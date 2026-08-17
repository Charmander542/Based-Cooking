from __future__ import annotations

from collections.abc import Iterator

from bs4 import Tag

from based_cooking.models import Recipe, RecipeStep
from based_cooking.sources.epub import EpubCookbookSource
from based_cooking.sources.html_utils import (
    dedupe,
    has_class,
    make_id,
    page_from_tree,
    parse_html,
    flatten_title,
    text_of,
)


class NigellaExpressSource(EpubCookbookSource):
    """Nigella Lawson — div.recipe wrappers with p.ingredient / div.step."""

    name = "nigella-express"

    def iter_recipes(self) -> Iterator[Recipe]:
        book = self.metadata().get("title") or "Nigella Express"
        for doc_path, html in self.iter_spine_xhtml():
            yield from self.parse_document(html, document_path=doc_path, book_title=book)

    def parse_document(
        self, html: str, *, document_path: str = "", book_title: str = ""
    ) -> list[Recipe]:
        soup = parse_html(html)
        if not soup.body:
            return []
        recipes: list[Recipe] = []
        for block in soup.body.select("div.recipe"):
            recipe = self._one(block, document_path, book_title)
            if recipe:
                recipes.append(recipe)
        return recipes

    def _one(self, block: Tag, document_path: str, book_title: str) -> Recipe | None:
        title_el = block.select_one(
            "h1.recipe-title, h1.recipe-title1, h1.recipe-title2, .recipe-title"
        )
        name = flatten_title(title_el)
        if not name or name.lower().startswith("for the "):
            return None
        page = page_from_tree(title_el or block)
        headnote = block.select_one("div.headnote")
        description = text_of(headnote)
        ingredients: list[str] = []
        for ing in block.select("div.ingredients p.ingredient, p.ingredient"):
            item = text_of(ing)
            if item:
                ingredients.append(item)
        # Section headers inside ingredients
        for hdr in block.select("h1.ingredients-title, .ingredients-title"):
            label = text_of(hdr)
            if label:
                ingredients.insert(0, f"[{label}]")

        steps: list[RecipeStep] = []
        for step in block.select("div.procedure div.step, div.step, p.step"):
            # Prefer leaf step paragraphs
            if step.name == "div" and step.find("p", class_="step"):
                continue
            text = text_of(step)
            if text:
                steps.append(RecipeStep(text=text))

        yield_text = ""
        for el in block.select("p.step1, p.makes, p.serves"):
            t = text_of(el)
            if t.lower().startswith(("makes", "serves", "serve")):
                yield_text = t
                break
        if not yield_text:
            for el in block.find_all("p"):
                t = text_of(el)
                if t.lower().startswith(("makes ", "serves ")):
                    yield_text = t
                    break

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
