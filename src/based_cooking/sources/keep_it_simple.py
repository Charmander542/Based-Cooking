from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from bs4 import Tag

from based_cooking.models import Recipe, RecipeStep
from based_cooking.sources.epub import EpubCookbookSource
from based_cooking.sources.html_utils import (
    dedupe,
    has_class,
    make_id,
    nodes_until,
    page_from_tree,
    parse_html,
    text_of,
)


class KeepItSimpleSource(EpubCookbookSource):
    """Matthew Bounds — h2.rt titles, div.ingredients, ol>li.rp steps."""

    name = "keep-it-simple"

    def iter_recipes(self) -> Iterator[Recipe]:
        book = self.metadata().get("title") or "Keep It Simple, Y'all"
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
        for el in soup.body.find_all(["h1", "h2"]):
            if has_class(el, "ct"):
                chapter = text_of(el)
                continue
            if not has_class(el, "rt"):
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
        nodes = nodes_until(
            heading,
            lambda n: n.name in {"h1", "h2"} and has_class(n, "rt", "ct"),
        )
        description = ""
        yield_parts: list[str] = []
        ingredients: list[str] = []
        steps: list[RecipeStep] = []

        for node in nodes:
            if not isinstance(node, Tag):
                continue
            if has_class(node, "rhn") and not description:
                description = text_of(node)
            elif has_class(node, "ry"):
                yield_parts.append(text_of(node))
            elif has_class(node, "ingredients") or (
                node.name == "div" and node.select_one("li.ril, p.ril")
            ):
                for li in node.select("li.ril, p.ril"):
                    item = text_of(li)
                    if item:
                        ingredients.append(item)
            elif node.name == "ol":
                for li in node.find_all("li", recursive=False):
                    text = text_of(li)
                    if text:
                        steps.append(RecipeStep(text=text))
            elif has_class(node, "rp"):
                text = text_of(node)
                if text:
                    steps.append(RecipeStep(text=text))

        if not ingredients and not steps:
            return None
        return Recipe(
            id=make_id(self.name, name, page, document_path),
            name=name,
            source=self.name,
            source_id=heading.get("id") or document_path,
            ingredients=dedupe(ingredients),
            steps=steps,
            description=description,
            yield_text=" | ".join(yield_parts),
            page=page,
            chapter=chapter,
            extras={"book": book_title, "document": document_path},
        )
