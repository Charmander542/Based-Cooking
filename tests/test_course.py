from __future__ import annotations

from based_cooking.course import infer_course
from based_cooking.models import Recipe, RecipeStep
from based_cooking.store import RecipeStore


def _recipe(**kwargs) -> Recipe:
    base = dict(
        id="x",
        name="X",
        source="test",
        source_id="x",
        ingredients=["1 onion"],
        steps=[RecipeStep(text="Cook.")],
    )
    base.update(kwargs)
    return Recipe(**base)


def test_infer_main_vs_side() -> None:
    roast = _recipe(
        id="m",
        name="Roast Chicken",
        chapter="POULTRY AND WILDFOWL",
        ingredients=["1 whole chicken", "2 tbsp butter", "1 tsp salt"],
    )
    roast.ensure_parsed()
    assert infer_course(roast) == "main"

    salad = _recipe(
        id="s",
        name="Tomato Cucumber Salad",
        chapter="SALADS",
        ingredients=["2 tomatoes", "1 cucumber", "2 tbsp olive oil"],
    )
    salad.ensure_parsed()
    assert infer_course(salad) == "side"

    cake = _recipe(
        id="d",
        name="Chocolate Cake",
        chapter="CAKES AND CUPCAKES",
        ingredients=["2 cups flour", "1 cup sugar", "2 eggs"],
    )
    cake.ensure_parsed()
    assert infer_course(cake) == "dessert"


def test_search_filters_by_course(tmp_path) -> None:
    store = RecipeStore(tmp_path)
    store.replace_all(
        [
            _recipe(
                id="main1",
                name="Chicken Stir Fry",
                chapter="MEAT",
                ingredients=["1 lb chicken", "2 cups rice", "1 onion"],
            ),
            _recipe(
                id="side1",
                name="Green Salad",
                chapter="SALADS",
                ingredients=["lettuce", "tomato", "olive oil"],
            ),
        ]
    )
    mains = store.search("", course="main", limit=10)
    assert mains and all(r.course == "main" for r in mains)
    assert all(r.id == "main1" for r in mains)

    sides = store.search("", course="side", limit=10)
    assert sides and all(r.course == "side" for r in sides)
