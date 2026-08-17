from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from based_cooking.ingredients import ParsedIngredient

# Approximate density helpers when converting volume ↔ mass for common pantry items.
# Values are grams per cup (US) unless noted.
GRAMS_PER_CUP: dict[str, float] = {
    "flour": 120,
    "sugar": 200,
    "brown sugar": 220,
    "butter": 227,
    "olive oil": 216,
    "oil": 218,
    "vegetable oil": 218,
    "milk": 244,
    "water": 237,
    "rice": 185,
    "oats": 90,
    "salt": 273,
    "honey": 340,
    "yogurt": 245,
    "sour cream": 230,
}

UNIT_TO_ML = {
    "tsp": 4.92892,
    "tbsp": 14.7868,
    "cup": 236.588,
    "floz": 29.5735,
    "ml": 1.0,
    "l": 1000.0,
}


@lru_cache(maxsize=1)
def load_nutrition_db(path: str | None = None) -> dict[str, Any]:
    """Load companion nutrition facts keyed by canonical ingredient name."""
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    packaged = resources.files("based_cooking").joinpath("data/nutrition_foods.json")
    if packaged.is_file():
        return json.loads(packaged.read_text(encoding="utf-8"))
    # Dev fallback when package data not installed yet
    fallback = Path(__file__).with_name("data") / "nutrition_foods.json"
    if fallback.exists():
        return json.loads(fallback.read_text(encoding="utf-8"))
    return {}


def lookup_food(item: str, db: dict[str, Any] | None = None) -> dict[str, Any] | None:
    db = db if db is not None else load_nutrition_db()
    key = item.casefold().strip()
    if key in db:
        return db[key]
    # soft match: try singular / aliases embedded in db keys
    if key.endswith("s") and key[:-1] in db:
        return db[key[:-1]]
    for candidate, payload in db.items():
        aliases = [a.casefold() for a in payload.get("aliases", [])]
        if key == candidate or key in aliases:
            return payload
        if key.endswith(candidate) or candidate.endswith(key):
            if abs(len(key) - len(candidate)) <= 4:
                return payload
    return None


def nutrition_for_ingredient(
    ing: ParsedIngredient,
    *,
    db: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Estimate nutrition for one parsed ingredient using the companion DB."""
    db = db if db is not None else load_nutrition_db()
    food = lookup_food(ing.item, db)
    if not food:
        return None
    per = food.get("per") or {}
    qty = ing.quantity if ing.quantity is not None else 1.0
    unit = ing.unit or "each"

    macros = _macros_for_amount(food, per, qty, unit, ing.item)
    if macros is None:
        return {
            "item": ing.item,
            "matched": food.get("name", ing.item),
            "quantity": qty,
            "unit": unit,
            "display": ing.display(),
            "allergens": list(food.get("allergens") or ing.allergens),
            "estimated": False,
            "note": "no convertible unit in nutrition DB",
        }
    return {
        "item": ing.item,
        "matched": food.get("name", ing.item),
        "quantity": qty,
        "unit": unit,
        "display": ing.display(),
        "allergens": list(food.get("allergens") or ing.allergens),
        "estimated": True,
        **macros,
    }


def nutrition_for_recipe(
    ingredients: list[ParsedIngredient],
    *,
    db: dict[str, Any] | None = None,
) -> dict[str, Any]:
    db = db if db is not None else load_nutrition_db()
    lines = []
    totals = {"kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carbs_g": 0.0, "fiber_g": 0.0}
    matched = 0
    for ing in ingredients:
        row = nutrition_for_ingredient(ing, db=db)
        if not row:
            lines.append(
                {
                    "item": ing.item,
                    "display": ing.display(),
                    "estimated": False,
                    "note": "unmatched ingredient",
                }
            )
            continue
        lines.append(row)
        if row.get("estimated"):
            matched += 1
            for k in totals:
                totals[k] += float(row.get(k, 0) or 0)
    return {
        "ingredients": lines,
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "matched": matched,
        "total_lines": len(ingredients),
        "coverage": round(matched / len(ingredients), 3) if ingredients else 0.0,
    }


def _macros_for_amount(
    food: dict[str, Any],
    per: dict[str, Any],
    qty: float,
    unit: str,
    item: str,
) -> dict[str, float] | None:
    if unit in per:
        base = per[unit]
        return {k: round(float(base.get(k, 0)) * qty, 2) for k in ("kcal", "protein_g", "fat_g", "carbs_g", "fiber_g")}

    # Convert via grams when possible
    grams = _to_grams(qty, unit, item, per)
    if grams is not None and "g" in per:
        base = per["g"]
        factor = grams
        return {
            k: round(float(base.get(k, 0)) * factor, 2)
            for k in ("kcal", "protein_g", "fat_g", "carbs_g", "fiber_g")
        }
    if grams is not None and "100g" in per:
        base = per["100g"]
        factor = grams / 100.0
        return {
            k: round(float(base.get(k, 0)) * factor, 2)
            for k in ("kcal", "protein_g", "fat_g", "carbs_g", "fiber_g")
        }
    return None


def _to_grams(qty: float, unit: str, item: str, per: dict[str, Any]) -> float | None:
    if unit == "g":
        return qty
    if unit == "kg":
        return qty * 1000
    if unit == "oz":
        return qty * 28.3495
    if unit == "lb":
        return qty * 453.592
    if unit == "stick" and "stick" in per:
        return None  # handled by direct per-unit
    if unit in UNIT_TO_ML:
        # prefer explicit grams-per-cup density
        density = GRAMS_PER_CUP.get(item.casefold())
        if density and unit == "cup":
            return qty * density
        if density:
            ml = qty * UNIT_TO_ML[unit]
            return ml * (density / UNIT_TO_ML["cup"])
        # water-like fallback for liquids if food declares density_g_per_ml
        return None
    return None
