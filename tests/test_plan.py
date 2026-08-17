from __future__ import annotations

from datetime import date
from pathlib import Path

from based_cooking.models import Recipe, RecipeStep
from based_cooking.plan import MealHistory, flavor_profile, plan_week
from based_cooking.servings import parse_servings, scale_recipe
from based_cooking.store import RecipeStore


def _recipe(**kwargs) -> Recipe:
    base = dict(
        id="x",
        name="X",
        source="test",
        source_id="x",
        ingredients=["1 onion"],
        steps=[RecipeStep(text="Cook.")],
        yield_text="4 servings",
    )
    base.update(kwargs)
    return Recipe(**base)


def test_parse_servings_ranges() -> None:
    assert parse_servings("4 servings") == 4
    assert parse_servings("Serves 6") == 6
    assert parse_servings("4 to 6 servings") == 5
    assert parse_servings("") == 4


def test_scale_recipe_doubles_quantities() -> None:
    recipe = _recipe(
        id="eggs",
        name="Scramble",
        ingredients=["2 large eggs", "1 tbsp butter", "1 tsp salt"],
        yield_text="2 servings",
    )
    scaled = scale_recipe(recipe, 4)
    by_item = {p.item: p for p in scaled.parsed_ingredients}
    assert by_item["egg"].quantity == 4
    assert by_item["butter"].quantity == 2
    assert "4 servings" in scaled.yield_text
    assert scaled.extras["scale_factor"] == 2.0
    # Original unchanged
    recipe.ensure_parsed()
    assert recipe.parsed_ingredients[0].quantity == 2


def test_plan_avoids_repeats_and_adjacent_same_protein(tmp_path) -> None:
    recipes = [
        _recipe(
            id="chicken-a",
            name="Roast Chicken",
            chapter="MEAT",
            ingredients=["1 lb chicken", "2 tbsp olive oil", "1 tsp salt", "1 lemon"],
            tags=["chicken"],
        ),
        _recipe(
            id="chicken-b",
            name="Chicken Stir Fry",
            chapter="MEAT",
            ingredients=["1 lb chicken", "2 tbsp soy sauce", "1 cup rice", "1 tbsp ginger"],
            tags=["chicken"],
        ),
        _recipe(
            id="beef-a",
            name="Beef Tacos",
            chapter="MEAT",
            ingredients=["1 lb beef", "2 tomatoes", "1 onion", "1 tsp cumin"],
            tags=["beef"],
        ),
        _recipe(
            id="salmon-a",
            name="Lemon Salmon",
            chapter="FISH",
            ingredients=[
                "1 lb salmon",
                "1 lemon",
                "2 tbsp olive oil",
                "1 tsp salt",
                "1 cup rice",
                "1 tomato",
            ],
            tags=["seafood"],
        ),
        _recipe(
            id="tofu-a",
            name="Tofu Curry",
            chapter="VEGETABLES",
            ingredients=["1 lb tofu", "1 onion", "1 tbsp curry", "1 cup coconut milk"],
            tags=["vegetarian"],
        ),
        _recipe(
            id="salad-a",
            name="Tomato Salad",
            chapter="SALADS",
            ingredients=["2 tomatoes", "1 cucumber", "2 tbsp olive oil"],
            tags=["salad"],
        ),
    ]
    store = RecipeStore(tmp_path)
    store.replace_all(recipes)

    history = MealHistory(tmp_path / "meal_history.jsonl")
    history.path.write_text(
        '{"date": "2026-08-01", "recipe_id": "chicken-a", "name": "Roast Chicken", "course": "main"}\n',
        encoding="utf-8",
    )

    plan = plan_week(
        store,
        days=4,
        servings=2,
        start=date(2026, 8, 17),
        with_sides=True,
        cooldown_days=21,
        history=history,
    )
    mains = [m for m in plan.meals if m.course == "main"]
    assert len(mains) == 4
    ids = [m.recipe.id for m in mains]
    assert "chicken-a" not in ids
    assert len(set(ids)) == 4
    assert mains[0].servings == 2
    assert mains[0].scale_factor == 0.5

    proteins = [flavor_profile(next(r for r in recipes if r.id == m.recipe.id)).proteins for m in mains]
    for a, b in zip(proteins, proteins[1:]):
        # Don't serve the same protein two days in a row when alternatives exist.
        assert not (a & b)


def test_history_blocks_recent_recipe(tmp_path) -> None:
    hist = MealHistory(tmp_path / "h.jsonl")
    hist.path.write_text(
        '{"date": "2026-08-10", "recipe_id": "abc", "course": "main"}\n',
        encoding="utf-8",
    )
    assert "abc" in hist.recent_ids(since=date(2026, 8, 17), cooldown_days=21)
    assert "abc" not in hist.recent_ids(since=date(2026, 8, 17), cooldown_days=5)
