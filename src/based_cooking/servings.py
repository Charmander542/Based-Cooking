from __future__ import annotations

import copy
import re
from dataclasses import replace

from based_cooking.ingredients import format_qty
from based_cooking.models import Recipe

DEFAULT_SERVINGS = 4.0

_RANGE = r"(?P<a>\d+(?:\.\d+)?)(?:\s*(?:-|–|—|to)\s*(?P<b>\d+(?:\.\d+)?))?"

_YIELD_PATTERNS = [
    re.compile(rf"(?:serves?|yields?|makes?)\s+(?:about\s+)?{_RANGE}\s*(?:servings?)?", re.I),
    re.compile(rf"{_RANGE}\s+servings?", re.I),
    re.compile(rf"(?:about\s+)?{_RANGE}\s+(?:people|persons?)", re.I),
]


def parse_servings(yield_text: str | None, *, default: float = DEFAULT_SERVINGS) -> float:
    """Best-effort serving count from cookbook yield strings."""
    text = (yield_text or "").strip()
    if not text:
        return default
    for pat in _YIELD_PATTERNS:
        match = pat.search(text)
        if not match:
            continue
        a = float(match.group("a"))
        b = match.group("b")
        if b:
            return (a + float(b)) / 2.0
        return a
    return default


def scale_factor(recipe: Recipe, servings: float, *, default: float = DEFAULT_SERVINGS) -> float:
    base = parse_servings(recipe.yield_text, default=default)
    if base <= 0:
        base = default
    if servings <= 0:
        raise ValueError("servings must be positive")
    return servings / base


def scale_recipe(recipe: Recipe, servings: float, *, default: float = DEFAULT_SERVINGS) -> Recipe:
    """Return a copy whose ingredient quantities match `servings` people."""
    recipe.ensure_parsed()
    base = parse_servings(recipe.yield_text, default=default)
    factor = scale_factor(recipe, servings, default=default)
    scaled_parsed = [ing.scaled(factor) for ing in recipe.parsed_ingredients]
    extras = dict(recipe.extras)
    extras.update(
        {
            "original_servings": base,
            "servings": servings,
            "scale_factor": round(factor, 4),
        }
    )
    original_yield = recipe.yield_text or f"{format_qty(base)} servings"
    new_yield = f"{format_qty(servings)} servings (scaled from {original_yield})"
    return replace(
        recipe,
        parsed_ingredients=scaled_parsed,
        ingredients=[ing.display() for ing in scaled_parsed] or list(recipe.ingredients),
        yield_text=new_yield,
        extras=extras,
        steps=copy.deepcopy(recipe.steps),
        tags=list(recipe.tags),
        allergens=list(recipe.allergens),
    )


def merge_shopping_list(recipes: list[Recipe]) -> list[dict]:
    """Collapse scaled parsed ingredients into a shopping list."""
    buckets: dict[tuple[str, str], dict] = {}
    leftovers: list[dict] = []
    for recipe in recipes:
        recipe.ensure_parsed()
        for ing in recipe.parsed_ingredients:
            item = (ing.item or "").casefold().strip()
            if not item:
                leftovers.append({"item": ing.display(), "quantity": ing.quantity, "unit": ing.unit})
                continue
            unit = ing.unit or "each"
            key = (item, unit)
            if ing.quantity is None:
                leftovers.append({"item": ing.display(), "quantity": None, "unit": unit})
                continue
            slot = buckets.get(key)
            if slot is None:
                buckets[key] = {
                    "item": item,
                    "unit": unit,
                    "quantity": ing.quantity,
                    "optional": ing.optional,
                }
            else:
                slot["quantity"] += ing.quantity
                slot["optional"] = slot["optional"] and ing.optional
    merged = sorted(buckets.values(), key=lambda row: row["item"])
    for row in merged:
        row["display"] = f"{format_qty(row['quantity'])} {row['unit']} {row['item']}".replace(
            " each ", " "
        )
        if row["unit"] == "each":
            row["display"] = f"{format_qty(row['quantity'])} {row['item']}"
    merged.extend(leftovers)
    return merged
