from __future__ import annotations

import re
import warnings

from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

from based_cooking.sources.epub import clean_text, nearest_page, page_from_element, slugify

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def parse_html(html: str) -> BeautifulSoup:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        return BeautifulSoup(html, "lxml")


def has_class(el: Tag | None, *names: str) -> bool:
    if el is None:
        return False
    classes = set(el.get("class") or [])
    return any(name in classes for name in names)


def class_tokens(el: Tag | None) -> set[str]:
    if el is None:
        return set()
    return set(el.get("class") or [])


def text_of(el: Tag | None) -> str:
    if el is None:
        return ""
    return clean_text(el.get_text(" ", strip=True))


def flatten_title(el: Tag | None) -> str:
    """Flatten small-caps / decorative spans (Nigella) without injecting spaces."""
    if el is None:
        return ""
    # Prefer no-separator join so "A"+"VOCADO" => "AVOCADO"
    text = el.get_text("", strip=False)
    text = clean_text(text)
    # Collapse leftover single-letter gaps like "C RAYFISH" if any remain
    text = re.sub(r"\b([A-Z])\s+(?=[A-Z]{2,})", r"\1", text)
    return text


def page_from_tree(node: Tag | None) -> int | None:
    if node is None:
        return None
    page = nearest_page(node)
    if page is not None:
        return page
    # Anchor ids like page14, page-58, page_101, page15
    for anchor in node.find_all("a", id=True):
        match = re.search(r"page[_-]?(\d+)", str(anchor.get("id") or ""), re.I)
        if match:
            return int(match.group(1))
    for anchor in node.find_all_previous("a", id=True, limit=30):
        match = re.search(r"page[_-]?(\d+)", str(anchor.get("id") or ""), re.I)
        if match:
            return int(match.group(1))
    # Some books only put page ids on ancestors
    parent = node
    while parent is not None:
        for el in [parent, *parent.find_all(True, limit=5)]:
            page = page_from_element(el)
            if page is not None:
                return page
            eid = el.get("id") if isinstance(el, Tag) else None
            if eid:
                match = re.search(r"page[_-]?(\d+)", str(eid), re.I)
                if match:
                    return int(match.group(1))
        parent = parent.parent if isinstance(parent, Tag) else None
    return None


def nodes_until(start: Tag, stop_pred) -> list:
    nodes: list = []
    for sib in start.next_siblings:
        if isinstance(sib, Tag) and stop_pred(sib):
            break
        nodes.append(sib)
    return nodes


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def make_id(source: str, name: str, page: int | None, suffix: str = "") -> str:
    return slugify(f"{source}-{name}-{page if page is not None else 'np'}-{suffix}")


__all__ = [
    "parse_html",
    "has_class",
    "class_tokens",
    "text_of",
    "flatten_title",
    "page_from_tree",
    "nodes_until",
    "dedupe",
    "make_id",
    "clean_text",
    "slugify",
]
