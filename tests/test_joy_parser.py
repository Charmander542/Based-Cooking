from __future__ import annotations

from pathlib import Path

import pytest

from based_cooking.models import Recipe, RecipeStep
from based_cooking.sources.joy_of_cooking import JoyOfCookingSource

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def stocks_html() -> str:
    return (FIXTURES / "joy_stocks_snippet.xhtml").read_text(encoding="utf-8")


@pytest.fixture
def poultry_html() -> str:
    return (FIXTURES / "joy_poultry_snippet.xhtml").read_text(encoding="utf-8")


def test_parses_recipe_count_and_ignores_non_recipe_headings(stocks_html: str) -> None:
    source = JoyOfCookingSource.__new__(JoyOfCookingSource)
    recipes = source.parse_document(stocks_html, document_path="part04.xhtml", book_title="Joy of Cooking")
    names = [r.name for r in recipes]
    assert names == ["BROWN BEEF STOCK", "WHITE VEAL STOCK"]
    assert "TOOLS FOR MAKING STOCK" not in names
    assert "ABOUT MEAT AND POULTRY STOCKS" not in names


def test_brown_beef_stock_fields(stocks_html: str) -> None:
    source = JoyOfCookingSource.__new__(JoyOfCookingSource)
    recipes = source.parse_document(stocks_html, document_path="part04.xhtml", book_title="Joy of Cooking")
    beef = recipes[0]

    assert beef.name == "BROWN BEEF STOCK"
    assert beef.yield_text == "About 8 cups"
    assert "Please read About Meat and Poultry Stocks" in beef.description
    assert beef.page == 72
    assert beef.chapter == "STOCKS AND SOUPS"
    assert beef.section == "ABOUT MEAT AND POULTRY STOCKS"
    assert "5 pounds meaty beef bones" in beef.ingredients
    assert "2 carrots, cut into 2-inch pieces" in beef.ingredients
    assert "Cold water to cover" in beef.ingredients
    assert any("Preheat the oven to 425" in step.text for step in beef.steps)
    # Interleaved: instruction that introduces carrots should carry those ingredients
    add_step = next(s for s in beef.steps if s.text == "Add:" and "2 carrots" in " ".join(s.ingredients))
    assert "2 medium unpeeled onions, quartered" in add_step.ingredients
    assert len(beef.ingredients) >= 10


def test_pagebreak_inside_title_updates_page(stocks_html: str) -> None:
    source = JoyOfCookingSource.__new__(JoyOfCookingSource)
    recipes = source.parse_document(stocks_html, document_path="part04.xhtml", book_title="Joy of Cooking")
    veal = recipes[1]
    assert veal.name == "WHITE VEAL STOCK"
    assert veal.page == 76
    assert "4 to 5 pounds veal knuckles or meaty bones" in veal.ingredients


def test_poultry_dinner_recipe_shape(poultry_html: str) -> None:
    source = JoyOfCookingSource.__new__(JoyOfCookingSource)
    recipes = source.parse_document(
        poultry_html, document_path="part14.xhtml", book_title="Joy of Cooking"
    )
    assert len(recipes) == 2
    hens = recipes[0]
    mushrooms = recipes[1]

    assert hens.yield_text == "4 servings"
    assert hens.page == 409
    assert any("Cornish hens" in ing for ing in hens.ingredients)
    assert any("vegetable oil" in ing for ing in hens.ingredients)
    assert mushrooms.name == "CHICKEN BREASTS BAKED ON A BED OF MUSHROOMS"
    assert mushrooms.page == 409  # pagebreak inside later ingredient should not rewind start page
    assert any("chicken breasts" in ing for ing in mushrooms.ingredients)
    assert "chicken" in mushrooms.tags


def test_recipe_serialization_roundtrip() -> None:
    recipe = Recipe(
        id="demo",
        name="Test Soup",
        source="joy-of-cooking",
        source_id="x",
        ingredients=["1 onion"],
        steps=[RecipeStep(text="Add:", ingredients=["1 onion"])],
        description="A soup",
        page=10,
    )
    restored = Recipe.from_dict(recipe.to_dict())
    assert restored.name == "Test Soup"
    assert restored.steps[0].ingredients == ["1 onion"]
    assert "Test Soup" in restored.search_blob()
