from __future__ import annotations

from based_cooking.models import Recipe, RecipeStep
from based_cooking.store import RecipeStore


def _sample_recipes() -> list[Recipe]:
    return [
        Recipe(
            id="joc-beef-stock",
            name="BROWN BEEF STOCK",
            source="joy-of-cooking",
            source_id="part04_sub002_01",
            description="A foundational brown stock.",
            yield_text="About 8 cups",
            ingredients=["5 pounds meaty beef bones", "2 carrots", "Cold water to cover"],
            steps=[
                RecipeStep(text="Roast the bones.", ingredients=["5 pounds meaty beef bones"]),
                RecipeStep(text="Simmer for 6 to 8 hours."),
            ],
            page=75,
            chapter="STOCKS AND SOUPS",
            section="ABOUT MEAT AND POULTRY STOCKS",
            tags=["soup", "beef"],
        ),
        Recipe(
            id="joc-cornish-hens",
            name="ROAST CORNISH HENS",
            source="joy-of-cooking",
            source_id="part14_sub010_04",
            description="Crispy roast birds for dinner.",
            yield_text="4 servings",
            ingredients=["2 large Cornish hens", "2 tablespoons vegetable oil", "1 teaspoon salt"],
            steps=[RecipeStep(text="Roast at 450°F until 170°F.")],
            page=409,
            chapter="POULTRY AND WILDFOWL",
            tags=["chicken"],
        ),
        Recipe(
            id="joc-mushroom-chicken",
            name="CHICKEN BREASTS BAKED ON A BED OF MUSHROOMS",
            source="joy-of-cooking",
            source_id="part14_sub010_07",
            description="Chicken with mushrooms and cream.",
            yield_text="4 to 6 servings",
            ingredients=["1 pound mushrooms", "4 chicken breasts", "heavy cream"],
            steps=[RecipeStep(text="Bake until 160°F.")],
            page=409,
            chapter="POULTRY AND WILDFOWL",
            tags=["chicken"],
        ),
    ]


def test_store_search_finds_dinner_candidates(tmp_path) -> None:
    store = RecipeStore(tmp_path)
    store.replace_all(_sample_recipes())

    hits = store.search("chicken dinner mushrooms", limit=5)
    assert hits
    assert hits[0].name == "CHICKEN BREASTS BAKED ON A BED OF MUSHROOMS"

    hens = store.search("Cornish hens", limit=5)
    assert any(r.name == "ROAST CORNISH HENS" for r in hens)

    stocks = store.search("beef bones stock", chapter="STOCKS")
    assert len(stocks) == 1
    assert stocks[0].page == 75


def test_store_get_and_jsonl_roundtrip(tmp_path) -> None:
    store = RecipeStore(tmp_path)
    recipes = _sample_recipes()
    store.replace_all(recipes)

    loaded = store.load_all()
    assert len(loaded) == 3
    got = store.get("joc-cornish-hens")
    assert got is not None
    assert got.yield_text == "4 servings"
    assert got.ingredients[0].startswith("2 large Cornish")
