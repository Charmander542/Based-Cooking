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


class MarthaOnePotSource(EpubCookbookSource):
    """Martha Stewart One Pot — div.recipe_title, IL_item, div.method."""

    name = "martha-one-pot"

    def iter_recipes(self) -> Iterator[Recipe]:
        book = self.metadata().get("title") or "One Pot"
        for doc_path, html in self.iter_spine_xhtml():
            yield from self.parse_document(html, document_path=doc_path, book_title=book)

    def parse_document(
        self, html: str, *, document_path: str = "", book_title: str = ""
    ) -> list[Recipe]:
        soup = parse_html(html)
        if not soup.body:
            return []
        recipes: list[Recipe] = []
        for title in soup.body.select("div.recipe_title, div.recipe_title2"):
            recipe = self._one(title, document_path, book_title)
            if recipe:
                recipes.append(recipe)
        return recipes

    def _one(self, title: Tag, document_path: str, book_title: str) -> Recipe | None:
        name = text_of(title)
        if not name:
            return None
        page = page_from_tree(title)
        nodes = nodes_until(
            title,
            lambda n: has_class(n, "recipe_title", "recipe_title2", "recipe_image"),
        )
        cook_time = ""
        description = ""
        yield_text = ""
        ingredients: list[str] = []
        steps: list[RecipeStep] = []

        for node in nodes:
            if not isinstance(node, Tag):
                continue
            tokens = class_tokens(node)
            if "cook_time" in tokens:
                cook_time = text_of(node)
            elif "headnote" in tokens:
                description = text_of(node)
                y = node.select_one("span.yield")
                if y:
                    yield_text = text_of(y)
                    # Strip yield from description if embedded
                    description = re.sub(
                        re.escape(yield_text), "", description, flags=re.I
                    ).strip()
            elif "ingredients" in tokens:
                for item in node.select("div.IL_item, div.IL_item_1"):
                    ingredients.append(text_of(item))
            elif any(t.startswith("IL_item") for t in tokens):
                ingredients.append(text_of(node))
            elif "method" in tokens or "method_step" in tokens:
                text = text_of(node)
                if text:
                    steps.append(RecipeStep(text=text))

        if not ingredients and not steps:
            return None
        extras = {"book": book_title, "document": document_path}
        if cook_time:
            extras["cook_time"] = cook_time
            if not yield_text:
                yield_text = cook_time
            elif cook_time not in yield_text:
                yield_text = f"{yield_text} | {cook_time}"

        return Recipe(
            id=make_id(self.name, name, page, title.get("id") or document_path),
            name=name,
            source=self.name,
            source_id=title.get("id") or document_path,
            ingredients=dedupe([i for i in ingredients if i]),
            steps=steps,
            description=description,
            yield_text=yield_text,
            page=page,
            chapter=book_title,
            extras=extras,
        )
