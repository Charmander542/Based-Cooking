from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from based_cooking.course import apply_course
from based_cooking.ingredients import matches_diet, parse_ingredients, recipe_allergens
from based_cooking.models import Recipe


class RecipeStore:
    """JSONL + SQLite FTS5 store optimized for LLM retrieval."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.data_dir / "recipes.jsonl"
        self.db_path = self.data_dir / "recipes.sqlite3"

    def replace_all(self, recipes: list[Recipe]) -> None:
        for recipe in recipes:
            recipe.ensure_parsed()
        self._write_jsonl(recipes)
        self._rebuild_sqlite(recipes)

    def upsert_source(self, source_name: str, recipes: list[Recipe]) -> list[Recipe]:
        """Replace all recipes from one source; keep other sources intact."""
        existing = [r for r in self.load_all() if r.source != source_name]
        merged = existing + recipes
        self.replace_all(merged)
        return merged

    def normalize_all(self) -> list[Recipe]:
        """Parse ingredients, allergens, and course (main/side/...) tags."""
        recipes = self.load_all()
        for recipe in recipes:
            recipe.parsed_ingredients = parse_ingredients(recipe.ingredients)
            recipe.allergens = recipe_allergens(recipe.parsed_ingredients)
            apply_course(recipe)
        self.replace_all(recipes)
        return recipes

    def _write_jsonl(self, recipes: list[Recipe]) -> None:
        with self.jsonl_path.open("w", encoding="utf-8") as fh:
            for recipe in recipes:
                fh.write(json.dumps(recipe.to_dict(), ensure_ascii=False) + "\n")

    def _rebuild_sqlite(self, recipes: list[Recipe]) -> None:
        if self.db_path.exists():
            self.db_path.unlink()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE recipes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source TEXT,
                    source_id TEXT,
                    description TEXT,
                    yield_text TEXT,
                    page INTEGER,
                    chapter TEXT,
                    section TEXT,
                    url TEXT,
                    course TEXT,
                    ingredients_json TEXT,
                    steps_json TEXT,
                    tags_json TEXT,
                    extras_json TEXT,
                    parsed_ingredients_json TEXT,
                    allergens_json TEXT,
                    search_blob TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE recipes_fts USING fts5(
                    name,
                    description,
                    ingredients,
                    steps,
                    chapter,
                    section,
                    tags,
                    allergens,
                    content='recipes',
                    content_rowid='rowid'
                )
                """
            )
            for recipe in recipes:
                recipe.ensure_parsed()
                ingredients_json = json.dumps(recipe.ingredients, ensure_ascii=False)
                steps_json = json.dumps(
                    [s.to_dict() for s in recipe.steps], ensure_ascii=False
                )
                tags_json = json.dumps(recipe.tags, ensure_ascii=False)
                extras_json = json.dumps(recipe.extras, ensure_ascii=False)
                parsed_json = json.dumps(
                    [p.to_dict() for p in recipe.parsed_ingredients], ensure_ascii=False
                )
                allergens_json = json.dumps(recipe.allergens, ensure_ascii=False)
                steps_text = " ".join(
                    f"{s.text} {' '.join(s.ingredients)}" for s in recipe.steps
                )
                ingredients_text = " ".join(
                    [*(recipe.ingredients), *(p.display() for p in recipe.parsed_ingredients)]
                )
                cur = conn.execute(
                    """
                    INSERT INTO recipes (
                        id, name, source, source_id, description, yield_text, page,
                        chapter, section, url, course, ingredients_json, steps_json, tags_json,
                        extras_json, parsed_ingredients_json, allergens_json, search_blob
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        recipe.id,
                        recipe.name,
                        recipe.source,
                        recipe.source_id,
                        recipe.description,
                        recipe.yield_text,
                        recipe.page,
                        recipe.chapter,
                        recipe.section,
                        recipe.url,
                        recipe.course,
                        ingredients_json,
                        steps_json,
                        tags_json,
                        extras_json,
                        parsed_json,
                        allergens_json,
                        recipe.search_blob(),
                    ),
                )
                rowid = cur.lastrowid
                conn.execute(
                    """
                    INSERT INTO recipes_fts (
                        rowid, name, description, ingredients, steps, chapter, section, tags, allergens
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rowid,
                        recipe.name,
                        recipe.description,
                        ingredients_text,
                        steps_text,
                        recipe.chapter,
                        recipe.section,
                        " ".join(recipe.tags),
                        " ".join(recipe.allergens),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def load_all(self) -> list[Recipe]:
        if not self.jsonl_path.exists():
            return []
        recipes: list[Recipe] = []
        with self.jsonl_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                recipes.append(Recipe.from_dict(json.loads(line)))
        return recipes

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        chapter: str | None = None,
        max_page: int | None = None,
        min_page: int | None = None,
        source: str | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        diet: str | None = None,
        course: str | None = None,
    ) -> list[Recipe]:
        """
        Full-text search with optional ingredient / dietary / course filters.

        `include`: ingredients that must all appear (e.g. tomato, garlic).
        `exclude`: allergen or ingredient tokens to ban (e.g. peanut, dairy, cilantro).
        `diet`: vegetarian | vegan | gluten_free | dairy_free | nut_free | ...
        `course`: main | side | appetizer | dessert | breakfast | drink | sauce | bread | staple
        """
        include = [t for t in (include or []) if t.strip()]
        exclude = [t for t in (exclude or []) if t.strip()]
        course = (course or "").casefold().strip() or None
        effective_query = (query or "").strip() or " ".join(include) or (course or "")
        if not self.db_path.exists():
            return self._fallback_search(
                effective_query,
                limit=limit,
                source=source,
                include=include,
                exclude=exclude,
                diet=diet,
                course=course,
            )

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            if effective_query:
                sql = """
                    SELECT recipes.*, bm25(recipes_fts) AS score
                    FROM recipes_fts
                    JOIN recipes ON recipes.rowid = recipes_fts.rowid
                    WHERE recipes_fts MATCH ?
                """
                params: list[object] = [_fts_query(effective_query)]
            else:
                sql = "SELECT recipes.*, 0 AS score FROM recipes WHERE 1=1"
                params = []
            if chapter:
                sql += " AND recipes.chapter LIKE ?"
                params.append(f"%{chapter}%")
            if source:
                sql += " AND recipes.source = ?"
                params.append(source)
            if course:
                sql += " AND lower(recipes.course) = ?"
                params.append(course)
            if min_page is not None:
                sql += " AND recipes.page >= ?"
                params.append(min_page)
            if max_page is not None:
                sql += " AND recipes.page <= ?"
                params.append(max_page)
            fetch = max(limit * 8, 60)
            if include or exclude or diet or course:
                fetch = max(fetch, limit * 20, 200)
            if effective_query:
                sql += " ORDER BY score LIMIT ?"
            else:
                sql += " LIMIT ?"
            params.append(fetch)

            rows = conn.execute(sql, params).fetchall()
            recipes = [_row_to_recipe(row) for row in rows]
            recipes = [
                r
                for r in recipes
                if _passes_restrictions(
                    r, include=include, exclude=exclude, diet=diet, course=course
                )
            ]
            if include and len(recipes) < limit:
                recipes = _ingredient_scan(
                    self,
                    include=include,
                    exclude=exclude,
                    diet=diet,
                    course=course,
                    source=source,
                    chapter=chapter,
                    limit=max(limit * 3, 40),
                )
            return _rerank(effective_query or " ".join(include), recipes)[:limit]
        finally:
            conn.close()

    def get(self, recipe_id: str) -> Recipe | None:
        if not self.db_path.exists():
            for recipe in self.load_all():
                if recipe.id == recipe_id:
                    return recipe
            return None
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM recipes WHERE id = ?", (recipe_id,)
            ).fetchone()
            return _row_to_recipe(row) if row else None
        finally:
            conn.close()

    def _fallback_search(
        self,
        query: str,
        *,
        limit: int,
        source: str | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        diet: str | None = None,
        course: str | None = None,
    ) -> list[Recipe]:
        tokens = [t.casefold() for t in query.split() if t.strip()]
        scored: list[Recipe] = []
        for recipe in self.load_all():
            if source and recipe.source != source:
                continue
            if not _passes_restrictions(
                recipe,
                include=include,
                exclude=exclude,
                diet=diet,
                course=course,
            ):
                continue
            blob = recipe.search_blob().casefold()
            if any(t in blob for t in tokens) or not tokens:
                scored.append(recipe)
        return _rerank(query, scored)[:limit]


def _has_ingredient(recipe: Recipe, token: str) -> bool:
    needle = token.casefold().strip().replace("_", " ")
    if not needle:
        return True
    recipe.ensure_parsed()
    haystacks = [
        *(p.item.casefold() for p in recipe.parsed_ingredients if p.item),
        *(ing.casefold() for ing in recipe.ingredients),
        *(p.display().casefold() for p in recipe.parsed_ingredients),
    ]
    for part in haystacks:
        if needle == part or needle in part:
            return True
    return False


def _passes_restrictions(
    recipe: Recipe,
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    diet: str | None = None,
    course: str | None = None,
) -> bool:
    recipe.ensure_parsed()
    if course and (recipe.course or "").casefold() != course.casefold():
        return False
    allergens = set(a.casefold() for a in recipe.allergens)
    if diet and not matches_diet(list(allergens), diet):
        return False
    if include:
        for token in include:
            if not _has_ingredient(recipe, token):
                return False
    if not exclude:
        return True
    blob_parts = [
        *recipe.ingredients,
        *(p.item for p in recipe.parsed_ingredients),
        *(p.display() for p in recipe.parsed_ingredients),
        *recipe.allergens,
    ]
    blob = " ".join(blob_parts).casefold()
    for token in exclude:
        t = token.casefold().strip().replace("-", "_")
        if not t:
            continue
        if t in allergens or t.replace("_", " ") in allergens:
            return False
        needle = t.replace("_", " ")
        if needle in blob:
            return False
    return True


def _ingredient_scan(
    store: RecipeStore,
    *,
    include: list[str],
    exclude: list[str] | None,
    diet: str | None,
    course: str | None = None,
    source: str | None,
    chapter: str | None,
    limit: int,
) -> list[Recipe]:
    """Scan recipes when FTS candidates miss required ingredients."""
    hits: list[Recipe] = []
    for recipe in store.load_all():
        if source and recipe.source != source:
            continue
        if chapter and chapter.casefold() not in (recipe.chapter or "").casefold():
            continue
        if not _passes_restrictions(
            recipe,
            include=include,
            exclude=exclude,
            diet=diet,
            course=course,
        ):
            continue
        hits.append(recipe)
        if len(hits) >= limit:
            break
    return hits


def _fts_query(query: str) -> str:
    """OR tokens so meal prompts like 'chicken dinner mushrooms' still hit."""
    tokens = [t for t in query.replace('"', " ").split() if t]
    if not tokens:
        return '""'
    if len(tokens) == 1:
        return f'"{tokens[0]}"'
    return " OR ".join(f'"{t}"' for t in tokens)


def _rerank(query: str, recipes: list[Recipe]) -> list[Recipe]:
    stop = {
        "a",
        "an",
        "and",
        "for",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
        "easy",
        "dinner",
        "recipe",
        "recipes",
        "weeknight",
        "quick",
    }
    q = query.casefold().strip()
    tokens = [t for t in q.split() if t and t not in stop]

    def score(recipe: Recipe) -> tuple:
        name = recipe.name.casefold()
        exact = 0 if name == q else 1
        phrase = 0 if q and q in name else 1
        token_hits = -sum(1 for t in tokens if t in name)
        ingredient_hits = -sum(
            1 for t in tokens if any(t in ing.casefold() for ing in recipe.ingredients)
        )
        # Prefer titles that contain more distinctive query terms.
        return (exact, phrase, token_hits, ingredient_hits, len(recipe.name), recipe.name)

    return sorted(recipes, key=score)


def _row_to_recipe(row: sqlite3.Row) -> Recipe:
    keys = set(row.keys())
    data = {
        "id": row["id"],
        "name": row["name"],
        "source": row["source"],
        "source_id": row["source_id"],
        "description": row["description"],
        "yield_text": row["yield_text"],
        "page": row["page"],
        "chapter": row["chapter"],
        "section": row["section"],
        "url": row["url"] if "url" in keys else "",
        "course": row["course"] if "course" in keys else "",
        "ingredients": json.loads(row["ingredients_json"] or "[]"),
        "steps": json.loads(row["steps_json"] or "[]"),
        "tags": json.loads(row["tags_json"] or "[]"),
        "extras": json.loads(row["extras_json"] or "{}"),
        "parsed_ingredients": json.loads(
            row["parsed_ingredients_json"] if "parsed_ingredients_json" in keys else "[]"
        )
        if "parsed_ingredients_json" in keys
        else [],
        "allergens": json.loads(row["allergens_json"] if "allergens_json" in keys else "[]")
        if "allergens_json" in keys
        else [],
    }
    return Recipe.from_dict(data)
