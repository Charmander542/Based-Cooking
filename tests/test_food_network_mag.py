from __future__ import annotations

from pathlib import Path

from based_cooking.sources import resolve_source
from based_cooking.sources.food_network_mag import FoodNetworkMagazineSource
from based_cooking.sources.food_network_search import (
    FoodNetworkSearcher,
    _parse_search_html,
    _title_similarity,
)

FIXTURES = Path(__file__).parent / "fixtures" / "fnmag"


def test_resolve_food_network_magazine_epub() -> None:
    epubs = list(Path(".").glob("Food Network Magazine*.epub"))
    if not epubs:
        return
    source = resolve_source(epubs[0])
    assert isinstance(source, FoodNetworkMagazineSource)


def test_parse_salad_page_titles_and_body() -> None:
    html = (FIXTURES / "salad_page.xhtml").read_text(encoding="utf-8")
    source = FoodNetworkMagazineSource.__new__(FoodNetworkMagazineSource)
    recipes = source.parse_document(html, document_path="page_241.xhtml", page=241)
    names = [r.name.upper() for r in recipes]
    assert any("CAESAR" in n for n in names)
    caesar = next(r for r in recipes if "Caesar" in r.name or "CAESAR" in r.name.upper())
    assert caesar.page == 241
    assert caesar.steps
    assert caesar.ingredients or len(caesar.steps[0].text) > 20


def test_parse_textbox_pancake_page() -> None:
    html = (FIXTURES / "pancake_page.xhtml").read_text(encoding="utf-8")
    source = FoodNetworkMagazineSource.__new__(FoodNetworkMagazineSource)
    recipes = source.parse_document(html, document_path="page_118.xhtml", page=118)
    assert len(recipes) >= 3
    assert any("pancake" in r.name.lower() for r in recipes)
    assert all(r.steps for r in recipes)


def test_title_similarity_and_search_html_parse() -> None:
    assert _title_similarity("Caesar Salad", "caesar salad recipe") >= 0.9
    assert _title_similarity("Grilled Vegetable Potato Salad", "Grilled Caesar Salad") < 0.7
    html = """
    <a href="https://www.foodnetwork.com/recipes/food-network-kitchen/caesar-salad-1957611">x</a>
    <a href="https://www.foodnetwork.com/recipes/ree-drummond/caesar-salad-recipe-2040807">y</a>
    """
    hits = _parse_search_html(html)
    assert len(hits) == 2
    assert "food-network-kitchen" in hits[0]["url"]


def test_searcher_find_best_url_with_stub() -> None:
    class Stub(FoodNetworkSearcher):
        def __init__(self):
            self.delay_seconds = 0
            self.timeout = 1
            self._cache = {}
            self._last_request = 0.0

        def search(self, query: str):
            return [
                {
                    "url": "https://www.foodnetwork.com/recipes/food-network-kitchen/caesar-salad-1957611",
                    "title": "caesar salad",
                },
                {
                    "url": "https://www.foodnetwork.com/recipes/someone/grilled-caesar-salad-1",
                    "title": "grilled caesar salad",
                },
            ]

    best = Stub().find_best_url("Caesar Salad")
    assert best is not None
    assert "food-network-kitchen" in best["url"]
    assert best["score"] >= 0.9
