from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from bs4 import Tag

from based_cooking.models import Recipe, RecipeStep
from based_cooking.sources.epub import EpubCookbookSource
from based_cooking.sources.html_utils import (
    class_tokens,
    dedupe,
    has_class,
    make_id,
    nodes_until,
    page_from_tree,
    parse_html,
    text_of,
)


class SheetPanSuppersSource(EpubCookbookSource):
    """Molly Gilbert — p.RH titles, p.RI ingredients, p.RP steps."""

    name = "sheet-pan-suppers"

    def iter_recipes(self) -> Iterator[Recipe]:
        book = self.metadata().get("title") or "Sheet Pan Suppers"
        chapter = ""
        for doc_path, html in self.iter_spine_xhtml():
            recipes, chapter = self._parse(html, doc_path, book, chapter)
            yield from recipes

    def parse_document(
        self, html: str, *, document_path: str = "", book_title: str = ""
    ) -> list[Recipe]:
        recipes, _ = self._parse(html, document_path, book_title, "")
        return recipes

    def _parse(
        self, html: str, document_path: str, book_title: str, chapter: str
    ) -> tuple[list[Recipe], str]:
        soup = parse_html(html)
        if not soup.body:
            return [], chapter
        recipes: list[Recipe] = []
        for el in soup.body.find_all(["h1", "h2", "p"]):
            tokens = class_tokens(el)
            if "CT" in tokens:
                chapter = text_of(el)
                continue
            if "RH" not in tokens:
                continue
            recipe = self._one(el, document_path, book_title, chapter)
            if recipe:
                recipes.append(recipe)
        return recipes, chapter

    def _one(
        self, heading: Tag, document_path: str, book_title: str, chapter: str
    ) -> Recipe | None:
        name = text_of(heading)
        if not name:
            return None
        page = page_from_tree(heading)
        nodes = nodes_until(heading, lambda n: n.name == "p" and "RH" in class_tokens(n))
        description_parts: list[str] = []
        yield_text = ""
        ingredients: list[str] = []
        steps: list[RecipeStep] = []
        seen_ri = False

        for node in nodes:
            if not isinstance(node, Tag):
                continue
            tokens = class_tokens(node)
            if "RY" in tokens:
                yield_text = text_of(node)
            elif "RI" in tokens:
                seen_ri = True
                item = text_of(node)
                if item:
                    ingredients.append(item)
            elif "RP" in tokens:
                text = text_of(node)
                if text:
                    steps.append(RecipeStep(text=text))
            elif "RPH" in tokens:
                continue
            elif node.name == "p" and tokens.intersection({"noindent", "indentb", "indent"}):
                if not seen_ri:
                    description_parts.append(text_of(node))

        if not ingredients and not steps:
            return None
        return Recipe(
            id=make_id(self.name, name, page, document_path),
            name=name,
            source=self.name,
            source_id=heading.get("id") or document_path,
            ingredients=dedupe(ingredients),
            steps=steps,
            description=" ".join(p for p in description_parts if p),
            yield_text=yield_text,
            page=page,
            chapter=chapter,
            extras={"book": book_title, "document": document_path},
        )
