from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from pathlib import Path
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup, NavigableString, Tag

from based_cooking.models import Recipe, RecipeStep
from based_cooking.sources.base import RecipeSource

_OPF_NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}


class EpubCookbookSource(RecipeSource):
    """
    Generic EPUB reader with a conservative recipe heuristic.

    Cookbook-specific subclasses should override `parse_document` for
    accurate extraction. This base class still yields something useful for
    many cookbooks that use recipe headings + ingredient lists.
    """

    name = "epub"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self._meta: dict[str, str] | None = None

    def metadata(self) -> dict[str, str]:
        if self._meta is not None:
            return self._meta
        with zipfile.ZipFile(self.path) as zf:
            opf_path = self._find_opf(zf)
            root = ET.fromstring(zf.read(opf_path))
            title_el = root.find(".//dc:title", _OPF_NS)
            creator_el = root.find(".//dc:creator", _OPF_NS)
            self._meta = {
                "title": (title_el.text or "").strip() if title_el is not None else "",
                "creator": (creator_el.text or "").strip() if creator_el is not None else "",
                "opf_path": opf_path,
            }
        return self._meta

    def iter_spine_xhtml(self) -> Iterator[tuple[str, str]]:
        with zipfile.ZipFile(self.path) as zf:
            opf_path = self.metadata()["opf_path"]
            root = ET.fromstring(zf.read(opf_path))
            opf_dir = str(Path(opf_path).parent).replace("\\", "/")
            if opf_dir == ".":
                opf_dir = ""

            manifest: dict[str, str] = {}
            for item in root.iter():
                if item.tag.endswith("item") and "id" in item.attrib and "href" in item.attrib:
                    manifest[item.attrib["id"]] = item.attrib["href"]

            spine_ids: list[str] = []
            for itemref in root.iter():
                if itemref.tag.endswith("itemref") and "idref" in itemref.attrib:
                    spine_ids.append(itemref.attrib["idref"])

            for idref in spine_ids:
                href = manifest.get(idref)
                if not href:
                    continue
                if not href.lower().endswith((".xhtml", ".html", ".htm", ".xml")):
                    continue
                full = f"{opf_dir}/{href}" if opf_dir else href
                full = full.lstrip("./")
                try:
                    raw = zf.read(full).decode("utf-8", errors="replace")
                except KeyError:
                    leaf = href.split("/")[-1]
                    candidates = [n for n in zf.namelist() if n.endswith(leaf)]
                    if not candidates:
                        continue
                    full = candidates[0]
                    raw = zf.read(full).decode("utf-8", errors="replace")
                yield full, raw

    def iter_recipes(self) -> Iterator[Recipe]:
        book_title = self.metadata().get("title") or self.path.stem
        for doc_path, html in self.iter_spine_xhtml():
            yield from self.parse_document(html, document_path=doc_path, book_title=book_title)

    def parse_document(
        self,
        html: str,
        *,
        document_path: str = "",
        book_title: str = "",
    ) -> list[Recipe]:
        soup = BeautifulSoup(html, "lxml")
        recipes: list[Recipe] = []
        if not soup.body:
            return recipes

        headings = soup.body.find_all(["h1", "h2", "h3", "h4"])
        for heading in headings:
            name = clean_text(heading.get_text(" ", strip=True))
            if not name or len(name) < 3:
                continue
            block_nodes = collect_until_next_heading(heading)
            ingredients = []
            for node in block_nodes:
                if isinstance(node, Tag) and node.name == "ul":
                    for li in node.find_all("li"):
                        item = clean_text(li.get_text(" ", strip=True))
                        if item:
                            ingredients.append(item)
            if len(ingredients) < 2:
                continue
            steps: list[RecipeStep] = []
            for node in block_nodes:
                if isinstance(node, Tag) and node.name == "p":
                    text = clean_text(node.get_text(" ", strip=True))
                    if text:
                        steps.append(RecipeStep(text=text))
            page = nearest_page(heading)
            recipe_id = slugify(f"{book_title}-{document_path}-{name}-{page}")
            recipes.append(
                Recipe(
                    id=recipe_id,
                    name=name,
                    source=self.name,
                    source_id=document_path,
                    ingredients=ingredients,
                    steps=steps,
                    description=steps[0].text if steps else "",
                    page=page,
                    chapter=book_title,
                )
            )
        return recipes

    @staticmethod
    def _find_opf(zf: zipfile.ZipFile) -> str:
        if "META-INF/container.xml" in zf.namelist():
            container = ET.fromstring(zf.read("META-INF/container.xml"))
            rootfile = container.find(
                ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
            )
            if rootfile is not None and rootfile.attrib.get("full-path"):
                return rootfile.attrib["full-path"]
        for name in zf.namelist():
            if name.endswith(".opf"):
                return name
        raise FileNotFoundError("No OPF found in EPUB")


def page_from_element(el: object) -> int | None:
    if not isinstance(el, Tag):
        return None
    epub_type = el.get("epub:type") or el.get("type") or ""
    role = el.get("role") or ""
    if "pagebreak" in str(epub_type) or role == "doc-pagebreak":
        for key in ("title", "aria-label"):
            raw = el.get(key)
            if raw and str(raw).isdigit():
                return int(raw)
        eid = el.get("id") or ""
        match = re.search(r"(\d+)", str(eid))
        if match:
            return int(match.group(1))
    return None


def nearest_page(node: Tag) -> int | None:
    inside = node.find(attrs={"role": "doc-pagebreak"})
    if not inside:
        inside = node.find(attrs={"epub:type": "pagebreak"})
    if inside:
        page = page_from_element(inside)
        if page is not None:
            return page

    for prev in node.find_all_previous():
        page = page_from_element(prev)
        if page is not None:
            return page
    return None


def collect_until_next_heading(heading: Tag, stop_names: set[str] | None = None) -> list:
    stop = stop_names or {"h1", "h2", "h3", "h4"}
    nodes: list = []
    for sib in heading.next_siblings:
        if isinstance(sib, Tag) and sib.name in stop:
            break
        if isinstance(sib, NavigableString) and not str(sib).strip():
            continue
        nodes.append(sib)
    return nodes


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u00a0", " ")
    # Normalize odd EPUB spaces that appear as "1 ½"
    text = re.sub(r"\s+", " ", text).strip()
    return text


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:120] or "recipe"
