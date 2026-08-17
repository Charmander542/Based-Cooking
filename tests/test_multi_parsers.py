from __future__ import annotations

from pathlib import Path

import pytest

from based_cooking.sources.food_lab import FoodLabSource
from based_cooking.sources.keep_it_simple import KeepItSimpleSource
from based_cooking.sources.martha import MarthaOnePotSource
from based_cooking.sources.nigella import NigellaExpressSource
from based_cooking.sources.sfah import SaltFatAcidHeatSource
from based_cooking.sources.sheet_pan import SheetPanSuppersSource
from based_cooking.sources.wok import WokSource

FIXTURES = Path(__file__).parent / "fixtures" / "multi"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_keep_it_simple_fixture() -> None:
    recipes = KeepItSimpleSource.__new__(KeepItSimpleSource).parse_document(
        _html("keep_simple_recipe.xhtml"), book_title="Keep It Simple"
    )
    assert len(recipes) == 1
    r = recipes[0]
    assert r.name == "Chicken and Wild Rice"
    assert r.page == 11
    assert any("wild rice" in i.lower() for i in r.ingredients)
    assert len(r.steps) >= 5
    assert "Servings" in r.yield_text


def test_sheet_pan_fixture() -> None:
    recipes = SheetPanSuppersSource.__new__(SheetPanSuppersSource).parse_document(
        _html("sheetpan_recipe.xhtml"), book_title="Sheet Pan Suppers"
    )
    assert len(recipes) == 1
    r = recipes[0]
    assert "Brie" in r.name
    assert any("strawberries" in i.lower() for i in r.ingredients)
    assert len(r.steps) >= 4
    assert "Serves" in r.yield_text


def test_nigella_fixture() -> None:
    recipes = NigellaExpressSource.__new__(NigellaExpressSource).parse_document(
        _html("nigella_recipe.xhtml"), book_title="Nigella Express"
    )
    assert len(recipes) == 1
    r = recipes[0]
    assert "AVOCADO" in r.name.upper()
    assert any("avocado" in i.lower() for i in r.ingredients)
    assert len(r.steps) >= 3
    assert r.yield_text.lower().startswith("serves")


def test_martha_fixture() -> None:
    recipes = MarthaOnePotSource.__new__(MarthaOnePotSource).parse_document(
        _html("martha_recipe.xhtml"), book_title="One Pot"
    )
    assert len(recipes) == 1
    r = recipes[0]
    assert "Beef Stew" in r.name
    assert any("beef chuck" in i.lower() for i in r.ingredients)
    assert len(r.steps) >= 2
    assert "SERVES" in r.yield_text.upper()


def test_sfah_fixture() -> None:
    recipes = SaltFatAcidHeatSource.__new__(SaltFatAcidHeatSource).parse_document(
        _html("sfah_recipe.xhtml"), book_title="Salt, Fat, Acid, Heat"
    )
    assert len(recipes) == 1
    r = recipes[0]
    assert "Cabbage Slaw" in r.name
    assert any("cabbage" in i.lower() for i in r.ingredients)
    assert len(r.steps) >= 3
    assert "Serves" in r.yield_text


def test_food_lab_fixture() -> None:
    recipes = FoodLabSource.__new__(FoodLabSource).parse_document(
        _html("foodlab_recipe.xhtml"), book_title="The Food Lab"
    )
    assert len(recipes) >= 1
    r = recipes[0]
    assert "POACHED EGGS" in r.name.upper() or "EGG" in r.name.upper()
    assert r.ingredients
    assert r.steps or r.description


def test_wok_fixture() -> None:
    recipes = WokSource.__new__(WokSource).parse_document(
        _html("wok_recipe.xhtml"), book_title="The Wok"
    )
    assert len(recipes) == 1
    r = recipes[0]
    assert "KUNG PAO" in r.name.upper()
    assert any("chicken" in i.lower() for i in r.ingredients)
    assert len(r.steps) >= 4
    assert "Serves" in r.yield_text
