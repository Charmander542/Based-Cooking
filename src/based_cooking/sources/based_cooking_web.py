from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from urllib.parse import urljoin, urlparse

from bs4 import Tag

from based_cooking.models import Recipe, RecipeStep
from based_cooking.sources.base import RecipeSource
from based_cooking.sources.html_utils import (
    dedupe,
    make_id,
    parse_html,
    text_of,
)

DEFAULT_BASE = "https://based.cooking/"
USER_AGENT = "BasedCookingScraper/0.1 (+https://based.cooking/; personal recipe index)"


class BasedCookingWebSource(RecipeSource):
    """
    Scraper for https://based.cooking/

    Lists recipes from the homepage `#artlist`, then fetches each recipe page
    for ingredients, directions, yield/time, tags, and canonical URL.
    """

    name = "based-cooking-web"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE,
        *,
        delay_seconds: float = 0.15,
        limit: int = 0,
        opener=None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.delay_seconds = max(0.0, delay_seconds)
        self.limit = limit
        self._opener = opener  # injectable for tests: callable(url) -> html str

    def fetch(self, url: str) -> str:
        if self._opener is not None:
            return self._opener(url)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.read().decode("utf-8", "replace")

    def iter_recipe_links(self) -> list[tuple[str, str, list[str]]]:
        """Return (url, title, tags) from the homepage recipe list."""
        html = self.fetch(self.base_url)
        soup = parse_html(html)
        links: list[tuple[str, str, list[str]]] = []
        seen: set[str] = set()
        artlist = soup.select_one("#artlist")
        items = artlist.find_all("li") if artlist else soup.find_all("li")
        for li in items:
            a = li.find("a", href=True)
            if not a:
                continue
            href = a["href"].strip()
            url = urljoin(self.base_url, href)
            if not self._is_recipe_url(url):
                continue
            if url in seen:
                continue
            seen.add(url)
            title = text_of(a) or url.rstrip("/").rsplit("/", 1)[-1]
            tags = _parse_data_tags(li.get("data-tags") or "")
            links.append((url, title, tags))
        return links

    def iter_recipes(self) -> Iterator[Recipe]:
        links = self.iter_recipe_links()
        if self.limit and self.limit > 0:
            links = links[: self.limit]
        for index, (url, list_title, list_tags) in enumerate(links):
            if index and self.delay_seconds:
                time.sleep(self.delay_seconds)
            try:
                html = self.fetch(url)
            except (urllib.error.URLError, TimeoutError, OSError):
                continue
            recipe = self.parse_recipe_page(
                html, url=url, fallback_title=list_title, fallback_tags=list_tags
            )
            if recipe is not None:
                yield recipe

    def parse_recipe_page(
        self,
        html: str,
        *,
        url: str,
        fallback_title: str = "",
        fallback_tags: list[str] | None = None,
    ) -> Recipe | None:
        soup = parse_html(html)
        article = soup.select_one("article") or soup.body
        if article is None:
            return None

        h1 = soup.select_one("h1")
        name = text_of(h1) or fallback_title
        name = re.sub(r"^[\W_]+|[\W_]+$", "", name).strip() or fallback_title
        if not name:
            return None

        description_parts: list[str] = []
        # Prefer heading text match over brittle NavigableString equality
        ingredients_h2 = None
        directions_h2 = None
        for heading in article.find_all(["h2", "h3"]):
            label = text_of(heading).casefold()
            if label == "ingredients":
                ingredients_h2 = heading
            elif label in {"directions", "direction", "steps", "method"}:
                directions_h2 = heading

        # Description: paragraphs before Ingredients heading
        for p in article.find_all("p"):
            if ingredients_h2 and _comes_after(p, ingredients_h2):
                break
            if p.find("img") and not text_of(p):
                continue
            text = text_of(p)
            if text:
                description_parts.append(text)

        meta_bits = _extract_meta_list(article, ingredients_h2)
        ingredients = _list_after_heading(ingredients_h2)
        steps = [
            RecipeStep(text=item) for item in _list_after_heading(directions_h2) if item
        ]

        tags = list(fallback_tags or [])
        taglist = article.select_one("div.taglist")
        if taglist:
            page_tags = [text_of(a) for a in taglist.find_all("a") if text_of(a)]
            tags = dedupe([*tags, *page_tags])
        else:
            keywords = soup.find("meta", attrs={"name": "keywords"})
            if keywords and keywords.get("content"):
                tags = dedupe(
                    [*tags, *[t.strip() for t in keywords["content"].split(",") if t.strip()]]
                )

        if not ingredients and not steps:
            return None

        slug = urlparse(url).path.strip("/") or make_id("bc", name, None)
        yield_text = " | ".join(meta_bits)
        return Recipe(
            id=make_id(self.name, slug, None),
            name=name,
            source=self.name,
            source_id=slug,
            ingredients=dedupe(ingredients),
            steps=steps,
            description=" ".join(description_parts).strip(),
            yield_text=yield_text,
            chapter="based.cooking",
            tags=[t.lower() for t in tags],
            url=url.rstrip("/") + "/",
            extras={"site": "based.cooking"},
        )

    @staticmethod
    def _is_recipe_url(url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc and "based.cooking" not in parsed.netloc:
            return False
        path = parsed.path.strip("/")
        if not path:
            return False
        if "/" in path:
            # skip /tags/foo etc.
            return False
        if path in {"tags", "index.xml", "sitemap.xml", "style.css", "favicon.svg"}:
            return False
        if path.endswith((".xml", ".css", ".js", ".png", ".jpg", ".webp", ".svg", ".ico")):
            return False
        return True


def _parse_data_tags(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []
    raw = raw.strip("[]")
    return [t.strip().lower() for t in re.split(r"[\s,]+", raw) if t.strip()]


def _comes_after(node: Tag, marker: Tag) -> bool:
    for prev in node.find_all_previous():
        if prev is marker:
            return True
    return False


def _extract_meta_list(article: Tag, ingredients_h2: Tag | None) -> list[str]:
    ingredients_list = _next_list(ingredients_h2)
    for ul in article.find_all("ul"):
        if ingredients_list is not None and ul is ingredients_list:
            continue
        if ingredients_h2 is not None and _comes_after(ul, ingredients_h2):
            continue
        texts = [text_of(li) for li in ul.find_all("li", recursive=False)]
        texts = [t for t in texts if t]
        if not texts:
            continue
        joined = " ".join(texts).lower()
        if any(
            key in joined
            for key in ("prep time", "cook time", "servings", "serves", "yield")
        ):
            return texts
    return []


def _next_list(heading: Tag | None) -> Tag | None:
    if heading is None:
        return None
    for sib in heading.next_siblings:
        if isinstance(sib, Tag) and sib.name in {"ul", "ol"}:
            return sib
    return None


def _list_after_heading(heading: Tag | None) -> list[str]:
    lst = _next_list(heading)
    if lst is None:
        return []
    items: list[str] = []
    for li in lst.find_all("li", recursive=False):
        text = text_of(li)
        if text:
            items.append(text)
    return items
