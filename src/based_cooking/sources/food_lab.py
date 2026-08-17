from __future__ import annotations

from collections.abc import Iterator

from bs4 import Tag

from based_cooking.models import Recipe, RecipeStep
from based_cooking.sources.epub import EpubCookbookSource
from based_cooking.sources.html_utils import (
    class_tokens,
    dedupe,
    make_id,
    nodes_until,
    page_from_tree,
    parse_html,
    text_of,
)


_TITLE_START = {"recipe_rt", "recipe_rt1a", "recipe_srt", "srecipe_rt", "srecipe_rt1a"}
_TITLE_CONT = {"recipe_rt1", "srecipe_rt1"}
_ING = {"recipe_i", "srecipe_i"}
_ING_HDR = {"recipe_ih", "recipe_ih1", "srecipe_ih", "srecipe_ih1"}
_STEPS = {"recipe_rsteps", "recipe_rsteps1", "srecipe_rsteps", "srecipe_rsteps1"}
_YIELD = {"recipe_y", "recipe_ym", "srecipe_y"}
_HEADNOTE = {
    "recipe_hnindnew",
    "recipe_vhn",
    "recipe_hn",
    "srecipe_hn",
    "noindentt",
}


class FoodLabSource(EpubCookbookSource):
    """Kenji López-Alt The Food Lab — recipe_rt* / recipe_i / recipe_rsteps*."""

    name = "food-lab"

    def iter_recipes(self) -> Iterator[Recipe]:
        book = self.metadata().get("title") or "The Food Lab"
        for doc_path, html in self.iter_spine_xhtml():
            yield from self.parse_document(html, document_path=doc_path, book_title=book)

    def parse_document(
        self, html: str, *, document_path: str = "", book_title: str = ""
    ) -> list[Recipe]:
        soup = parse_html(html)
        if not soup.body:
            return []
        recipes: list[Recipe] = []
        paragraphs = soup.body.find_all("p")
        i = 0
        while i < len(paragraphs):
            el = paragraphs[i]
            tokens = class_tokens(el)
            if not tokens.intersection(_TITLE_START):
                i += 1
                continue
            # Skip pure continuation titles handled by previous recipe
            name_parts = [text_of(el)]
            j = i + 1
            while j < len(paragraphs):
                nxt = paragraphs[j]
                nxt_tokens = class_tokens(nxt)
                if nxt_tokens.intersection(_TITLE_CONT):
                    name_parts.append(text_of(nxt))
                    j += 1
                    continue
                break
            start = el
            recipe = self._one(start, name_parts, document_path, book_title)
            if recipe:
                recipes.append(recipe)
            i = j if j > i else i + 1
        return recipes

    def _one(
        self,
        start: Tag,
        name_parts: list[str],
        document_path: str,
        book_title: str,
    ) -> Recipe | None:
        name = " ".join(p for p in name_parts if p).strip()
        if not name:
            return None
        page = page_from_tree(start)

        def stop(n: Tag) -> bool:
            tokens = class_tokens(n)
            if n.name != "p":
                return False
            if tokens.intersection(_TITLE_CONT):
                return False
            return bool(tokens.intersection(_TITLE_START))

        nodes = nodes_until(start, stop)
        # Also include continuation title siblings already consumed in name
        yield_text = ""
        description = ""
        ingredients: list[str] = []
        steps: list[RecipeStep] = []
        notes: list[str] = []
        seen_ing = False

        for node in nodes:
            if not isinstance(node, Tag):
                continue
            tokens = class_tokens(node)
            if tokens.intersection(_TITLE_CONT):
                continue
            if tokens.intersection(_YIELD):
                yield_text = text_of(node)
            elif tokens.intersection(_ING_HDR):
                label = text_of(node)
                if label:
                    ingredients.append(f"[{label}]")
            elif tokens.intersection(_ING):
                seen_ing = True
                item = text_of(node)
                if item:
                    ingredients.append(item)
            elif tokens.intersection(_STEPS):
                text = text_of(node)
                if text:
                    steps.append(RecipeStep(text=text))
            elif "recipe_n-copy" in tokens or "recipe_n" in tokens:
                notes.append(text_of(node))
            elif tokens.intersection(_HEADNOTE) or (
                node.name == "p"
                and not seen_ing
                and not steps
                and tokens.intersection({"noindent", "indent", "noindentt"})
            ):
                text = text_of(node)
                if text and not description:
                    description = text
                elif text and seen_ing and not steps:
                    # Instructional prose without numbered step class
                    steps.append(RecipeStep(text=text))
            elif seen_ing and node.name == "p" and tokens.intersection(
                {"noindentt", "noindent", "indent"}
            ):
                text = text_of(node)
                if text:
                    steps.append(RecipeStep(text=text))

        if notes and not description:
            description = " ".join(notes)
        elif notes:
            description = f"{description} {' '.join(notes)}".strip()

        if not ingredients and not steps:
            return None
        return Recipe(
            id=make_id(self.name, name, page, document_path),
            name=name,
            source=self.name,
            source_id=document_path,
            ingredients=dedupe(ingredients),
            steps=steps,
            description=description,
            yield_text=yield_text,
            page=page,
            chapter=book_title,
            extras={"book": book_title, "document": document_path},
        )
