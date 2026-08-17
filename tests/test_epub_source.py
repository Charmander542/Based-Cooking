from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from based_cooking.sources import WebRecipeSource, resolve_source
from based_cooking.sources.epub import EpubCookbookSource
from based_cooking.sources.joy_of_cooking import JoyOfCookingSource

ROOT = Path(__file__).resolve().parents[1]


def _find_joy_epub() -> Path | None:
    matches = list(ROOT.glob("*Joy of Cooking*.epub"))
    return matches[0] if matches else None


def test_resolve_source_picks_joy_adapter(tmp_path: Path) -> None:
    # Minimal EPUB with Joy title in OPF
    epub = tmp_path / "sample.epub"
    container = """<?xml version="1.0"?>
    <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
      <rootfiles>
        <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
      </rootfiles>
    </container>"""
    opf = """<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf" unique-identifier="id" version="3.0">
      <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>Joy of Cooking</dc:title>
        <dc:creator>Irma S. Rombauer</dc:creator>
      </metadata>
      <manifest>
        <item id="c1" href="chapter.xhtml" media-type="application/xhtml+xml"/>
      </manifest>
      <spine>
        <itemref idref="c1"/>
      </spine>
    </package>"""
    chapter = (Path(__file__).parent / "fixtures" / "joy_stocks_snippet.xhtml").read_text(
        encoding="utf-8"
    )
    with zipfile.ZipFile(epub, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("content.opf", opf)
        zf.writestr("chapter.xhtml", chapter)

    source = resolve_source(epub)
    assert isinstance(source, JoyOfCookingSource)
    recipes = source.extract()
    assert len(recipes) == 2
    assert recipes[0].name == "BROWN BEEF STOCK"


def test_web_source_is_stubbed() -> None:
    source = WebRecipeSource(["https://example.com/recipe"])
    with pytest.raises(NotImplementedError):
        list(source.iter_recipes())


@pytest.mark.integration
def test_real_joy_epub_extracts_thousands_of_recipes() -> None:
    epub = _find_joy_epub()
    if epub is None:
        pytest.skip("Joy of Cooking EPUB not present")

    source = JoyOfCookingSource(epub)
    meta = source.metadata()
    assert "Joy of Cooking" in meta["title"]

    recipes = source.extract()
    assert len(recipes) >= 2000
    assert sum(1 for r in recipes if r.ingredients) >= 1800
    assert sum(1 for r in recipes if r.page is not None) >= 1800

    # Spot-check known dinners from the book
    by_name = {r.name: r for r in recipes}
    assert "BROWN BEEF STOCK" in by_name
    beef = by_name["BROWN BEEF STOCK"]
    assert beef.page is not None
    assert any("beef bones" in i.lower() for i in beef.ingredients)
    assert beef.steps

    hens = next(r for r in recipes if r.name == "ROAST CORNISH HENS")
    assert hens.yield_text
    assert any("hens" in i.lower() for i in hens.ingredients)
