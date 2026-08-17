from __future__ import annotations

from pathlib import Path

from based_cooking.sources.based_cooking_web import BasedCookingWebSource
from based_cooking.sources import resolve_source

FIXTURES = Path(__file__).parent / "fixtures" / "web"


def _pages() -> dict[str, str]:
    return {
        "https://based.cooking/": (FIXTURES / "homepage_mini.html").read_text(encoding="utf-8"),
        "https://based.cooking/carbonara/": (FIXTURES / "carbonara.html").read_text(
            encoding="utf-8"
        ),
        "https://based.cooking/chicken-tikka-masala/": (FIXTURES / "tikka.html").read_text(
            encoding="utf-8"
        ),
    }


def test_resolve_based_cooking_url() -> None:
    source = resolve_source("https://based.cooking/")
    assert isinstance(source, BasedCookingWebSource)


def test_parse_carbonara_fixture() -> None:
    html = (FIXTURES / "carbonara.html").read_text(encoding="utf-8")
    source = BasedCookingWebSource()
    recipe = source.parse_recipe_page(
        html,
        url="https://based.cooking/carbonara/",
        fallback_title="Carbonara",
        fallback_tags=["italian"],
    )
    assert recipe is not None
    assert recipe.name == "Carbonara"
    assert recipe.url == "https://based.cooking/carbonara/"
    assert any("Spaghetti" in i for i in recipe.ingredients)
    assert len(recipe.steps) >= 5
    assert "Servings: 4" in recipe.yield_text
    assert "pasta" in recipe.tags
    assert "simple dish" in recipe.description.lower()


def test_parse_tikka_fixture() -> None:
    html = (FIXTURES / "tikka.html").read_text(encoding="utf-8")
    source = BasedCookingWebSource()
    recipe = source.parse_recipe_page(
        html, url="https://based.cooking/chicken-tikka-masala/"
    )
    assert recipe is not None
    assert "Tikka" in recipe.name
    assert any("yogurt" in i.lower() for i in recipe.ingredients)
    assert recipe.steps
    assert recipe.url.endswith("/chicken-tikka-masala/")


def test_full_extract_with_injected_fetcher() -> None:
    pages = _pages()

    def opener(url: str) -> str:
        key = url if url.endswith("/") else url + "/"
        if key in pages:
            return pages[key]
        # allow without trailing slash for base
        if url.rstrip("/") + "/" in pages:
            return pages[url.rstrip("/") + "/"]
        raise KeyError(url)

    source = BasedCookingWebSource(
        "https://based.cooking/", delay_seconds=0, opener=opener
    )
    # Missing zurich page should be skipped when fetch fails — provide stub empty skip
    def opener2(url: str) -> str:
        normalized = url if url.endswith("/") else url + "/"
        if "zurich" in normalized:
            raise OSError("missing on purpose")
        return opener(url)

    source = BasedCookingWebSource(
        "https://based.cooking/", delay_seconds=0, opener=opener2
    )
    recipes = source.extract()
    assert len(recipes) == 2
    by_name = {r.name: r for r in recipes}
    assert by_name["Carbonara"].url == "https://based.cooking/carbonara/"
    assert by_name["Chicken Tikka Masala"].ingredients
