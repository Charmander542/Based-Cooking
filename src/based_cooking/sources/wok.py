from __future__ import annotations

from collections.abc import Iterator

from bs4 import Tag

from based_cooking.models import Recipe, RecipeStep
from based_cooking.sources.epub import EpubCookbookSource
from based_cooking.sources.html_utils import (
    class_tokens,
    dedupe,
    has_class,
    make_id,
    page_from_tree,
    parse_html,
    text_of,
)


class WokSource(EpubCookbookSource):
    """Kenji López-Alt The Wok — chap_hd + ing-list + numberg directions."""

    name = "the-wok"

    def iter_recipes(self) -> Iterator[Recipe]:
        book = self.metadata().get("title") or "The Wok"
        for doc_path, html in self.iter_spine_xhtml():
            yield from self.parse_document(html, document_path=doc_path, book_title=book)

    def parse_document(
        self, html: str, *, document_path: str = "", book_title: str = ""
    ) -> list[Recipe]:
        soup = parse_html(html)
        if not soup.body:
            return []
        # Prefer documents that look like full recipes
        if not soup.select_one("p.ing-list, p.ing-h"):
            return []
        recipes: list[Recipe] = []
        for title in soup.body.select("p.chap_hd, p.recipe_rn"):
            # recipe_rn is often NOTES label inside tables — skip if it's NOTE
            name = text_of(title)
            if not name or name.upper() in {"NOTE", "NOTES"}:
                continue
            if has_class(title, "recipe_rn") and not has_class(title, "chap_hd"):
                # Only accept recipe_rn when used as a rare alt title with ingredients nearby
                continue
            recipe = self._one(title, soup, document_path, book_title)
            if recipe:
                recipes.append(recipe)
        return recipes

    def _one(
        self, title: Tag, soup, document_path: str, book_title: str
    ) -> Recipe | None:
        name = text_of(title)
        page = page_from_tree(title)
        yield_parts: list[str] = []
        for y in soup.select("p.old_ypara, p.old_yparab"):
            text = text_of(y)
            if text:
                yield_parts.append(text)
        # Pair Yield label if present
        yield_text = " | ".join(yield_parts[:3])

        description_parts: list[str] = []
        for note in soup.select("p.notep, p.noteps"):
            t = text_of(note)
            if t:
                description_parts.append(t)
        ing_h = soup.select_one("p.ing-h")
        for p in soup.select("p.noindent_para, p.noindent"):
            t = text_of(p)
            if not t or t.upper() in {"INGREDIENTS", "DIRECTIONS"}:
                continue
            if p.find_parent("div", class_="tbs"):
                continue
            if ing_h is not None:
                # Only keep headnotes that appear before the ingredients header
                try:
                    if not (
                        p is ing_h
                        or any(prev is p for prev in ing_h.find_all_previous())
                    ):
                        continue
                except Exception:
                    pass
            description_parts.append(t)
            break

        ingredients: list[str] = []
        for el in soup.select("p.ing-ts, p.ing-hb, p.ing-list"):
            tokens = class_tokens(el)
            text = text_of(el)
            if not text:
                continue
            if tokens.intersection({"ing-ts", "ing-hb"}):
                ingredients.append(f"[{text.rstrip(':')}]")
            else:
                ingredients.append(text)

        steps: list[RecipeStep] = []
        for step in soup.select("p.numberg"):
            text = text_of(step)
            if text:
                steps.append(RecipeStep(text=text))
        # Include mise-en-place lettered list as a step if present
        for ol in soup.select("ol.alp"):
            items = [text_of(li) for li in ol.find_all("li") if text_of(li)]
            if items:
                steps.append(
                    RecipeStep(
                        text="BEFORE YOU STIR-FRY, GET YOUR BOWLS READY:",
                        ingredients=items,
                    )
                )

        if len(ingredients) < 2 and not steps:
            return None
        return Recipe(
            id=make_id(self.name, name, page, document_path),
            name=name,
            source=self.name,
            source_id=document_path,
            ingredients=dedupe(ingredients),
            steps=steps,
            description=" ".join(description_parts).strip(),
            yield_text=yield_text,
            page=page,
            chapter=book_title,
            extras={"book": book_title, "document": document_path},
        )
