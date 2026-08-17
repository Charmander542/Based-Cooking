from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from based_cooking.models import Recipe, RecipeStep
from based_cooking.sources.epub import (
    EpubCookbookSource,
    clean_text,
    collect_until_next_heading,
    nearest_page,
    slugify,
)


class JoyOfCookingSource(EpubCookbookSource):
    """
    Parser for the Scribner Joy of Cooking EPUB markup.

    Recipes are `h3.h3rec` blocks. Ingredients live in `li.r-item` lists
    interleaved with instructional `p.noindent` / `p.indent` paragraphs.
    Page numbers come from EPUB3 pagebreak spans.
    """

    name = "joy-of-cooking"

    def __init__(self, path: str | Path) -> None:
        super().__init__(path)

    def iter_recipes(self) -> Iterator[Recipe]:
        book_title = self.metadata().get("title") or "Joy of Cooking"
        # Carry chapter/section across split part files (part09 → part09a, etc.).
        chapter = ""
        section = ""
        for doc_path, html in self.iter_spine_xhtml():
            recipes, chapter, section = self._parse_document_with_state(
                html,
                document_path=doc_path,
                book_title=book_title,
                chapter=chapter,
                section=section,
            )
            yield from recipes

    def parse_document(
        self,
        html: str,
        *,
        document_path: str = "",
        book_title: str = "",
        chapter: str = "",
        section: str = "",
    ) -> list[Recipe]:
        recipes, _, _ = self._parse_document_with_state(
            html,
            document_path=document_path,
            book_title=book_title,
            chapter=chapter,
            section=section,
        )
        return recipes

    def _parse_document_with_state(
        self,
        html: str,
        *,
        document_path: str = "",
        book_title: str = "",
        chapter: str = "",
        section: str = "",
    ) -> tuple[list[Recipe], str, str]:
        soup = BeautifulSoup(html, "lxml")
        if not soup.body:
            return [], chapter, section

        recipes: list[Recipe] = []

        for el in soup.body.find_all(["h1", "h2", "h3"]):
            classes = set(el.get("class") or [])
            if el.name == "h1" and "h1" in classes:
                chapter = clean_text(el.get_text(" ", strip=True))
                section = ""
                continue
            if el.name == "h2" and "h2" in classes:
                section = clean_text(el.get_text(" ", strip=True))
                continue
            if el.name != "h3" or "h3rec" not in classes:
                continue

            recipe = self._parse_recipe_heading(
                el,
                document_path=document_path,
                book_title=book_title,
                chapter=chapter,
                section=section,
            )
            if recipe is not None:
                recipes.append(recipe)
        return recipes, chapter, section

    def _parse_recipe_heading(
        self,
        heading: Tag,
        *,
        document_path: str,
        book_title: str,
        chapter: str,
        section: str,
    ) -> Recipe | None:
        name = clean_text(heading.get_text(" ", strip=True))
        if not name:
            return None

        page = nearest_page(heading)
        nodes = collect_until_next_heading(
            heading, stop_names={"h1", "h2", "h3", "h4"}
        )

        yield_text = ""
        description_parts: list[str] = []
        steps: list[RecipeStep] = []
        all_ingredients: list[str] = []
        pending_text = ""
        seen_ingredient_list = False

        i = 0
        while i < len(nodes):
            node = nodes[i]
            if not isinstance(node, Tag):
                i += 1
                continue

            classes = set(node.get("class") or [])

            if node.name == "p" and "noindentl" in classes:
                yield_text = clean_text(node.get_text(" ", strip=True))
                i += 1
                continue

            if node.name == "p" and classes.intersection({"noindent", "indent"}):
                text = clean_text(node.get_text(" ", strip=True))
                if not text:
                    i += 1
                    continue

                # Peek for following ingredient list(s)
                following_ingredients: list[str] = []
                j = i + 1
                while j < len(nodes):
                    nxt = nodes[j]
                    if not isinstance(nxt, Tag):
                        j += 1
                        continue
                    nxt_classes = set(nxt.get("class") or [])
                    if nxt.name == "ul" and (
                        "nonlist" in nxt_classes or nxt.find("li", class_="r-item")
                    ):
                        following_ingredients.extend(_list_ingredients(nxt))
                        j += 1
                        # JoC often has one list per instruction; stop after first batch
                        # but allow consecutive lists without intervening paragraphs.
                        continue
                    break

                if not seen_ingredient_list and not following_ingredients and not steps:
                    # Leading prose before the first "Add:" / ingredient cue.
                    description_parts.append(text)
                    i += 1
                    continue

                if following_ingredients:
                    seen_ingredient_list = True
                    all_ingredients.extend(following_ingredients)
                    steps.append(RecipeStep(text=text, ingredients=following_ingredients))
                    i = j
                    continue

                # Instruction without a trailing ingredient list
                if pending_text:
                    steps.append(RecipeStep(text=pending_text))
                    pending_text = ""
                steps.append(RecipeStep(text=text))
                i += 1
                continue

            if node.name == "ul" and (
                "nonlist" in classes or node.find("li", class_="r-item")
            ):
                items = _list_ingredients(node)
                if items:
                    seen_ingredient_list = True
                    all_ingredients.extend(items)
                    if steps and not steps[-1].ingredients:
                        steps[-1].ingredients.extend(items)
                    else:
                        steps.append(RecipeStep(text="", ingredients=items))
                i += 1
                continue

            i += 1

        if pending_text:
            steps.append(RecipeStep(text=pending_text))

        # Drop empty placeholder steps
        steps = [s for s in steps if s.text or s.ingredients]

        # Recipes must have either ingredients or instructional steps
        if not all_ingredients and not any(s.text for s in steps):
            return None

        # Deduplicate ingredients while preserving order
        seen: set[str] = set()
        unique_ingredients: list[str] = []
        for item in all_ingredients:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique_ingredients.append(item)

        heading_id = heading.get("id") or ""
        recipe_id = slugify(
            f"joc-{heading_id or name}-{page if page is not None else 'np'}"
        )

        return Recipe(
            id=recipe_id,
            name=name,
            source=self.name,
            source_id=heading_id or document_path,
            ingredients=unique_ingredients,
            steps=steps,
            description=" ".join(description_parts).strip(),
            yield_text=yield_text,
            page=page,
            chapter=chapter,
            section=section,
            tags=_infer_tags(name, chapter, section, unique_ingredients),
            extras={
                "book": book_title,
                "document": document_path,
                "anchor": heading_id,
            },
        )


def _list_ingredients(ul: Tag) -> list[str]:
    items: list[str] = []
    for li in ul.find_all("li", recursive=False):
        text = clean_text(li.get_text(" ", strip=True))
        if text:
            items.append(text)
    if not items:
        for li in ul.find_all("li"):
            text = clean_text(li.get_text(" ", strip=True))
            if text:
                items.append(text)
    return items


def _infer_tags(name: str, chapter: str, section: str, ingredients: list[str]) -> list[str]:
    tags: list[str] = []
    blob = f"{name} {chapter} {section}".lower()
    mapping = {
        "soup": ["soup", "stock", "broth", "chowder", "bisque"],
        "chicken": ["chicken", "poultry", "hens"],
        "beef": ["beef", "steak", "veal"],
        "pork": ["pork", "ham", "bacon"],
        "vegetarian": ["vegetable", "salad", "bean"],
        "dessert": ["cake", "cookie", "pie", "pudding", "ice cream"],
        "breakfast": ["pancake", "waffle", "egg", "breakfast"],
        "bread": ["bread", "biscuit", "muffin", "roll"],
        "sauce": ["sauce", "gravy", "dressing"],
        "seafood": ["fish", "shrimp", "salmon", "crab", "lobster", "clam"],
    }
    for tag, needles in mapping.items():
        if any(n in blob for n in needles):
            tags.append(tag)

    joined = " ".join(ingredients).lower()
    if "chicken" in joined and "chicken" not in tags:
        tags.append("chicken")
    return tags
