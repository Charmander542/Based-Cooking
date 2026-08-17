from __future__ import annotations

import re
from collections.abc import Iterator

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


_ITEM_CLASSES = {"item", "item1", "itemb", "itema"}


class SaltFatAcidHeatSource(EpubCookbookSource):
    """Samin Nosrat — h2.h2rec titles with p.item* ingredients and prose steps."""

    name = "salt-fat-acid-heat"

    def iter_recipes(self) -> Iterator[Recipe]:
        book = self.metadata().get("title") or "Salt, Fat, Acid, Heat"
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
            tokens = class_tokens(el)
            if tokens.intersection({"h2c", "h2c1", "h2d", "h2", "ct"}) and not tokens.intersection(
                {"h2rec", "h2rec1"}
            ):
                chapter = text_of(el) or chapter
                continue
            if el.name == "h1":
                chapter = text_of(el) or chapter
                continue
            if not tokens.intersection({"h2rec", "h2rec1"}):
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
            lambda n: n.name in {"h1", "h2"}
            and (
                has_class(n, "h2rec", "h2rec1")
                or n.name == "h1"
                or (n.name == "h2" and not has_class(n, "h2rec", "h2rec1") and bool(class_tokens(n) & {"h2", "ct"}))
            ),
        )
        yield_text = ""
        description = ""
        ingredients: list[str] = []
        steps: list[RecipeStep] = []
        seen_item = False

        for node in nodes:
            if not isinstance(node, Tag):
                continue
            if node.name == "h5":
                label = text_of(node)
                if "variation" in label.lower():
                    break
                if label:
                    ingredients.append(f"[{label}]")
                continue
            tokens = class_tokens(node)
            if "right2" in tokens:
                yield_text = text_of(node)
                continue
            if tokens.intersection(_ITEM_CLASSES):
                seen_item = True
                item = _normalize_fractions(text_of(node))
                if item:
                    ingredients.append(item)
                continue
            if node.name == "p" and tokens.intersection(
                {"noindent", "indent", "indent1"}
            ):
                text = _normalize_fractions(text_of(node))
                if not text:
                    continue
                if not seen_item and not steps:
                    if not description:
                        description = text
                    else:
                        description = f"{description} {text}"
                else:
                    steps.append(RecipeStep(text=text))

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
            chapter=chapter,
            extras={"book": book_title, "document": document_path},
        )


def _normalize_fractions(text: str) -> str:
    # BeautifulSoup already flattens <sup>1</sup>/<sub>2</sub> to "1 / 2"
    text = re.sub(r"(\d)\s*/\s*(\d)", r"\1/\2", text)
    return text
