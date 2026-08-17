from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from bs4 import NavigableString, Tag

from based_cooking.models import Recipe, RecipeStep
from based_cooking.sources.epub import EpubCookbookSource
from based_cooking.sources.html_utils import dedupe, make_id, parse_html, text_of

TITLE_P_CLASSES = {
    "narmal_020green",
    "narmal_020pink",
    "narmal_020red",
    "narmal_020redt",
    "narmal_020pinkt",
    "narmal_020g",
}
TITLE_SPAN_CLASSES = TITLE_P_CLASSES | {
    "LightOrange",
    "Orange2",
    "top_white",
    "top_whitew",
}
BOLD_ING_CLASSES = {"narmal_020bold", "Glypha", "Glypha-org-b"}


def _class_set(value) -> set[str]:
    if not value:
        return set()
    if isinstance(value, str):
        return {value}
    return set(value)


class FoodNetworkMagazineSource(EpubCookbookSource):
    """
    Food Network Magazine: 1,000 Easy Recipes (fixed-layout EPUB).

    Recipes are short magazine cards: colored titles + one-paragraph methods,
    or textbox cards with LightOrange titles. Optional Food Network website
    URL enrichment is applied after extraction via `attach_foodnetwork_urls`.
    """

    name = "food-network-magazine"

    def iter_recipes(self) -> Iterator[Recipe]:
        book = self.metadata().get("title") or "Food Network Magazine"
        for doc_path, html in self.iter_spine_xhtml():
            page = _page_from_path(doc_path)
            if page is not None and (page < 8 or page >= 380):
                # Skip covers/front matter and back index/metric charts.
                continue
            yield from self.parse_document(
                html, document_path=doc_path, book_title=book, page=page
            )

    def parse_document(
        self,
        html: str,
        *,
        document_path: str = "",
        book_title: str = "",
        page: int | None = None,
    ) -> list[Recipe]:
        soup = parse_html(html)
        if not soup.body:
            return []
        if page is None:
            page = _page_from_path(document_path)

        found: list[Recipe] = []
        seen: set[str] = set()

        def add(name: str, body: str, kind: str, body_el: Tag | None = None) -> None:
            name = _clean(name).rstrip(":")
            body = _clean(body)
            if not name or len(name) > 120:
                return
            if name.casefold() in {"ingredients", "directions", "serves", "metric charts"}:
                return
            key = f"{page}:{name.casefold()}"
            if key in seen:
                return
            seen.add(key)
            ingredients = _ingredients_from_element(body_el) or _ingredients_from_body(body)
            steps = [RecipeStep(text=body)] if body else []
            if not ingredients and not steps:
                return
            display_name = name.title() if name.isupper() else name
            found.append(
                Recipe(
                    id=make_id(self.name, display_name, page, document_path),
                    name=display_name,
                    source=self.name,
                    source_id=f"{document_path}#{name.casefold()}",
                    ingredients=ingredients,
                    steps=steps,
                    description="",
                    yield_text="",
                    page=page,
                    chapter=book_title,
                    tags=_infer_tags(display_name, body),
                    url="",
                    extras={
                        "book": book_title,
                        "document": document_path,
                        "card_kind": kind,
                    },
                )
            )

        # Textbox cards
        for div in soup.find_all("div", class_=True):
            classes = div.get("class") or []
            if not any(str(c).startswith("textbox") for c in classes):
                continue
            title_el = div.find(
                "span",
                class_=lambda c: bool(_class_set(c) & {"LightOrange", "Orange2"}),
            )
            if not title_el:
                continue
            title = text_of(title_el)
            full = text_of(div)
            body = full
            if title and full.upper().startswith(title.upper()):
                body = full[len(title) :].strip(" :-")
            add(title, body, "textbox", div)

        # Colored title paragraphs followed by body paragraph
        for p in soup.find_all("p"):
            classes = set(p.get("class") or [])
            if classes & TITLE_P_CLASSES:
                title = text_of(p)
                body = ""
                body_el = None
                for sib in p.next_siblings:
                    if isinstance(sib, Tag) and sib.name == "p":
                        body = text_of(sib)
                        body_el = sib
                        break
                add(title, body, "p-title", body_el)
                continue

            if "narmal_020" in classes:
                title = _leading_title_span(p)
                if not title:
                    continue
                full = text_of(p)
                body = full
                if full.upper().startswith(title.upper()):
                    body = full[len(title) :].strip(" :-")
                add(title, body, "span-prefix", p)

        # top_white titles with nearby body text
        for el in soup.find_all(
            class_=lambda c: bool(_class_set(c) & {"top_white", "top_whitew"})
        ):
            title = text_of(el)
            body = ""
            parent = el.parent
            if parent:
                full = text_of(parent)
                if title and full.upper().startswith(title.upper()):
                    body = full[len(title) :].strip(" :-")
            add(title, body, "top_white", parent if isinstance(parent, Tag) else None)

        return found


def attach_foodnetwork_urls(
    recipes: list[Recipe],
    *,
    delay_seconds: float = 0.25,
    limit: int = 0,
    searcher=None,
) -> list[Recipe]:
    """Enrich recipes with best-matching foodnetwork.com recipe URLs."""
    from based_cooking.sources.food_network_search import FoodNetworkSearcher

    engine = searcher or FoodNetworkSearcher(delay_seconds=delay_seconds)
    target = recipes if not limit else recipes[:limit]
    matched = 0
    searched = 0
    for recipe in target:
        searched += 1
        try:
            match = engine.find_best_url(recipe.name)
        except Exception as exc:
            search_url = engine.search_page_url(recipe.name)
            recipe.extras = {
                **recipe.extras,
                "foodnetwork_search_url": search_url,
                "foodnetwork_match_error": str(exc)[:200],
            }
            if not recipe.url:
                recipe.url = search_url
            continue
        if match:
            recipe.url = match["url"]
            recipe.extras = {
                **recipe.extras,
                "foodnetwork_match_title": match.get("title", ""),
                "foodnetwork_match_score": match.get("score", 0),
                "foodnetwork_search_url": match.get("search_url", ""),
            }
            matched += 1
        else:
            search_url = engine.search_page_url(recipe.name)
            recipe.extras = {
                **recipe.extras,
                "foodnetwork_search_url": search_url,
            }
            if not recipe.url:
                recipe.url = search_url
        if searched % 50 == 0:
            print(f"  matched {matched}/{searched}…")
    print(f"Food Network URL matches: {matched}/{searched}")
    return recipes


def _leading_title_span(p: Tag) -> str:
    for child in p.children:
        if isinstance(child, NavigableString) and not str(child).strip():
            continue
        if isinstance(child, Tag) and child.name == "span":
            classes = set(child.get("class") or [])
            if classes & TITLE_SPAN_CLASSES:
                return text_of(child)
        break
    return ""


def _ingredients_from_element(el: Tag | None) -> list[str]:
    if el is None:
        return []
    items: list[str] = []
    for span in el.find_all("span"):
        classes = set(span.get("class") or [])
        if classes & BOLD_ING_CLASSES:
            text = text_of(span).strip(" ,.;:")
            if text and len(text) > 1:
                items.append(text)
    return dedupe(items)


def _ingredients_from_body(body: str) -> list[str]:
    """Best-effort ingredient list from magazine prose (no separate list)."""
    if not body:
        return []
    candidates: list[str] = []
    for match in re.finditer(
        r"(\d[\d¼½¾⅓⅔⅛⅜⅝⅞/\s]*\s*(?:cups?|cup|tablespoons?|teaspoons?|tbsp|tsp|pounds?|lbs?|ounces?|oz|cloves?|cans?|slices?|large|medium|small)?\s+[a-zA-Z][\w\s\-']{2,40})",
        body,
        flags=re.I,
    ):
        item = _clean(match.group(1))
        if item and len(item) < 60:
            candidates.append(item)
    return dedupe(candidates)[:30]


def _infer_tags(name: str, body: str) -> list[str]:
    blob = f"{name} {body}".lower()
    tags = []
    mapping = {
        "salad": ["salad"],
        "chicken": ["chicken"],
        "beef": ["beef", "steak"],
        "pasta": ["pasta", "noodle", "spaghetti"],
        "soup": ["soup", "chowder", "stew"],
        "breakfast": ["pancake", "egg", "scramble", "muffin", "waffle"],
        "dessert": ["cookie", "cake", "pie", "ice cream", "brownie"],
        "smoothie": ["smoothie", "blend"],
        "sandwich": ["sandwich", "panini", "burger", "toast", "crostini"],
        "quick": ["quick", "easy", "minute"],
    }
    for tag, needles in mapping.items():
        if any(n in blob for n in needles):
            tags.append(tag)
    return tags


def _page_from_path(path: str) -> int | None:
    match = re.search(r"page_(\d+)", path)
    return int(match.group(1)) if match else None


def _clean(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text
