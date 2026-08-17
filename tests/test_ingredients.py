from __future__ import annotations

from based_cooking.ingredients import parse_ingredient, matches_diet, recipe_allergens
from based_cooking.models import Recipe, RecipeStep
from based_cooking.nutrition import nutrition_for_ingredient, nutrition_for_recipe
from based_cooking.store import RecipeStore


def test_parse_common_useful_units() -> None:
    egg = parse_ingredient("2 large eggs")
    assert egg.quantity == 2
    assert egg.unit == "each"
    assert egg.item == "egg"
    assert "egg" in egg.allergens
    assert egg.display() == "2 egg"

    butter = parse_ingredient("1 tablespoon unsalted butter, melted")
    assert butter.quantity == 1
    assert butter.unit == "tbsp"
    assert butter.item == "butter"
    assert butter.display().startswith("1 tbsp butter")

    onion = parse_ingredient("1 onion")
    assert onion.quantity == 1
    assert onion.unit == "each"
    assert onion.item == "onion"

    salt = parse_ingredient("1 tsp kosher salt")
    assert salt.quantity == 1
    assert salt.unit == "tsp"
    assert salt.item == "salt"


def test_vague_units_become_tsp() -> None:
    pinch = parse_ingredient("Pinch of salt")
    assert pinch.unit == "tsp"
    assert pinch.quantity is not None
    assert pinch.quantity < 0.2
    assert pinch.item == "salt"
    assert "smidge" not in pinch.display().casefold()

    dash = parse_ingredient("A dash of cinnamon")
    assert dash.unit == "tsp"
    assert dash.item == "cinnamon"


def test_nutrition_lookup_for_butter() -> None:
    butter = parse_ingredient("2 tbsp butter")
    row = nutrition_for_ingredient(butter)
    assert row is not None
    assert row["estimated"] is True
    assert row["kcal"] > 150
    assert row["fat_g"] > 20


def test_store_exclusion_and_diet_filters(tmp_path) -> None:
    recipes = [
        Recipe(
            id="pb",
            name="Peanut Noodles",
            source="test",
            source_id="1",
            ingredients=["1/2 cup peanut butter", "8 ounces pasta", "2 tbsp soy sauce"],
            steps=[RecipeStep(text="Toss hot noodles with sauce.")],
            tags=["pasta"],
        ),
        Recipe(
            id="salad",
            name="Tomato Cucumber Salad",
            source="test",
            source_id="2",
            ingredients=["2 tomatoes", "1 cucumber", "2 tbsp olive oil", "1 tsp salt"],
            steps=[RecipeStep(text="Chop and dress.")],
            tags=["salad"],
        ),
        Recipe(
            id="chicken",
            name="Chicken and Rice",
            source="test",
            source_id="3",
            ingredients=["1 lb chicken", "1 cup rice", "1 onion"],
            steps=[RecipeStep(text="Simmer until done.")],
            tags=["chicken"],
        ),
        Recipe(
            id="salsa",
            name="Fresh Salsa",
            source="test",
            source_id="4",
            ingredients=["3 tomatoes", "1 onion", "1 jalapeno", "2 tbsp lime juice"],
            steps=[RecipeStep(text="Chop and mix.")],
            tags=["sauce"],
        ),
    ]
    store = RecipeStore(tmp_path)
    store.replace_all(recipes)

    no_peanut = store.search("noodles dinner", exclude=["peanut"], limit=10)
    assert all(r.id != "pb" for r in no_peanut)

    vegetarian = store.search("tomato salad rice", diet="vegetarian", limit=10)
    assert all(r.id != "chicken" for r in vegetarian)
    assert any(r.id == "salad" for r in vegetarian)

    dairy_ok = store.search("salad", diet="dairy_free", limit=5)
    assert any(r.id == "salad" for r in dairy_ok)

    with_tomato = store.search("", include=["tomato"], limit=10)
    assert {r.id for r in with_tomato} == {"salad", "salsa"}

    tomato_onion = store.search("dinner", include=["tomato", "onion"], limit=10)
    assert tomato_onion
    assert all(r.id == "salsa" for r in tomato_onion)


def test_normalize_populates_allergens(tmp_path) -> None:
    store = RecipeStore(tmp_path)
    store.replace_all(
        [
            Recipe(
                id="x",
                name="Butter Eggs",
                source="test",
                source_id="x",
                ingredients=["2 eggs", "1 tbsp butter"],
                steps=[RecipeStep(text="Scramble.")],
            )
        ]
    )
    recipes = store.normalize_all()
    assert recipes[0].parsed_ingredients
    allergens = set(recipes[0].allergens)
    assert "egg" in allergens
    assert "dairy" in allergens
    assert matches_diet(list(allergens), "vegan") is False

    totals = nutrition_for_recipe(recipes[0].parsed_ingredients)
    assert totals["matched"] >= 2
    assert totals["totals"]["protein_g"] > 0


def test_recipe_allergens_helper() -> None:
    parsed = [
        parse_ingredient("1 cup milk"),
        parse_ingredient("2 eggs"),
    ]
    assert recipe_allergens(parsed) == ["dairy", "egg"]
