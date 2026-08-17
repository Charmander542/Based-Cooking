from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

from based_cooking.models import Recipe
from based_cooking.servings import merge_shopping_list, scale_recipe
from based_cooking.store import RecipeStore, _passes_restrictions

PANTRY_STAPLES = {
    "salt",
    "pepper",
    "water",
    "oil",
    "olive oil",
    "vegetable oil",
    "sugar",
    "flour",
    "butter",
    "onion",
    "garlic",
    "shallot",
    "scallion",
    "carrot",
    "celery",
    "lemon",
    "lime",
    "parsley",
}

PROTEIN_NEEDLES = {
    "chicken": ("chicken", "hen", "turkey"),
    "beef": ("beef", "steak", "burger"),
    "pork": ("pork", "bacon", "ham", "sausage", "prosciutto"),
    "lamb": ("lamb",),
    "fish": ("salmon", "tuna", "cod", "fish", "trout", "halibut"),
    "shellfish": ("shrimp", "prawn", "crab", "lobster", "clam", "mussel", "scallop"),
    "egg": ("egg",),
    "tofu": ("tofu", "tempeh"),
    "bean": ("bean", "lentil", "chickpea", "black bean"),
}

FLAVOR_FAMILIES = {
    "tomato": ("tomato", "marinara", "passata"),
    "soy": ("soy sauce", "ginger", "sesame", "miso", "teriyaki"),
    "spicy": ("chili", "chilli", "cayenne", "jalapeno", "jalapeño", "hot sauce", "gochujang", "harissa"),
    "herb": ("basil", "parsley", "thyme", "rosemary", "oregano", "cilantro", "dill", "mint"),
    "citrus": ("lemon", "lime", "orange"),
    "cream": ("cream", "cheese", "yogurt", "ricotta", "parmesan", "cheddar"),
    "curry": ("curry", "cumin", "turmeric", "garam", "coriander", "cardamom"),
    "smoky": ("smoked", "bacon", "paprika", "chipotle"),
    "garlic": ("garlic",),
    "sweet": ("honey", "maple", "brown sugar"),
    "nutty": ("peanut", "almond", "walnut", "sesame"),
}

DISH_FAMILIES = (
    ("soup", ("soup", "chowder", "bisque", "stew", "chili", "chilli", "gumbo")),
    ("pasta", ("pasta", "spaghetti", "lasagna", "lasagne", "noodle", "ramen", "macaroni")),
    ("salad", ("salad", "slaw")),
    ("sandwich", ("sandwich", "panini", "burger", "taco", "burrito", "wrap")),
    ("pizza", ("pizza",)),
    ("stir-fry", ("stir-fry", "stir fry", "wok", "fried rice")),
    ("roast", ("roast", "baked", "sheet pan")),
    ("curry", ("curry", "tikka", "masala")),
    ("grill", ("grill", "kebab", "broil")),
    ("casserole", ("casserole", "gratin", "bake")),
    ("breakfast", ("pancake", "waffle", "omelet", "omelette", "scramble")),
)

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


TOKEN_STOP = PANTRY_STAPLES | {
    "fresh",
    "dried",
    "ground",
    "minced",
    "chopped",
    "sliced",
    "large",
    "small",
    "medium",
    "optional",
    "white",
    "black",
    "red",
    "green",
    "cup",
    "tbsp",
    "tsp",
    "ounce",
    "ounces",
    "pound",
    "pounds",
    "the",
    "and",
    "with",
    "for",
}

PROTEIN_TOKENS = {
    "chicken",
    "turkey",
    "hen",
    "duck",
    "beef",
    "steak",
    "pork",
    "bacon",
    "ham",
    "sausage",
    "lamb",
    "salmon",
    "tuna",
    "cod",
    "fish",
    "shrimp",
    "prawn",
    "crab",
    "lobster",
    "mussel",
    "clam",
    "tofu",
    "tempeh",
}


@dataclass(slots=True)
class FlavorProfile:
    items: frozenset[str]
    proteins: frozenset[str]
    flavors: frozenset[str]
    dish_family: str
    name_tokens: frozenset[str]
    overlap_tokens: frozenset[str]


@dataclass(slots=True)
class PlannedMeal:
    day: str
    date: str
    course: str
    recipe: Recipe
    servings: float
    scale_factor: float


@dataclass
class MealPlan:
    start: str
    days: int
    servings: float
    meals: list[PlannedMeal] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)

    def mains(self) -> list[Recipe]:
        return [m.recipe for m in self.meals if m.course == "main"]

    def all_recipes(self) -> list[Recipe]:
        return [m.recipe for m in self.meals]

    def shopping_list(self) -> list[dict]:
        return merge_shopping_list(self.all_recipes())

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "days": self.days,
            "servings": self.servings,
            "scores": self.scores,
            "meals": [
                {
                    "day": m.day,
                    "date": m.date,
                    "course": m.course,
                    "id": m.recipe.id,
                    "name": m.recipe.name,
                    "source": m.recipe.source,
                    "url": m.recipe.url,
                    "page": m.recipe.page,
                    "servings": m.servings,
                    "scale_factor": m.scale_factor,
                    "yield": m.recipe.yield_text,
                    "allergens": m.recipe.allergens,
                    "ingredients": [p.display() for p in m.recipe.parsed_ingredients],
                }
                for m in self.meals
            ],
            "shopping_list": self.shopping_list(),
        }


class MealHistory:
    """JSONL log of cooked/planned recipes used to space repeats."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def recent_ids(self, *, since: date, cooldown_days: int) -> set[str]:
        cutoff = since - timedelta(days=cooldown_days)
        ids: set[str] = set()
        for row in self.load():
            raw = row.get("date") or ""
            try:
                when = date.fromisoformat(raw[:10])
            except ValueError:
                continue
            if when >= cutoff:
                rid = row.get("recipe_id") or row.get("id")
                if rid:
                    ids.add(rid)
        return ids

    def append(self, plan: MealPlan) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            for meal in plan.meals:
                fh.write(
                    json.dumps(
                        {
                            "date": meal.date,
                            "day": meal.day,
                            "recipe_id": meal.recipe.id,
                            "name": meal.recipe.name,
                            "course": meal.course,
                            "servings": meal.servings,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )


def flavor_profile(recipe: Recipe) -> FlavorProfile:
    recipe.ensure_parsed()
    items = {
        (p.item or "").casefold().strip()
        for p in recipe.parsed_ingredients
        if (p.item or "").strip()
    }
    blob = " ".join(
        [
            recipe.name,
            recipe.chapter,
            " ".join(recipe.ingredients),
            " ".join(items),
        ]
    ).casefold()

    proteins = set()
    for label, needles in PROTEIN_NEEDLES.items():
        if any(n in blob for n in needles):
            proteins.add(label)
    if "meat" in {a.casefold() for a in recipe.allergens} and not proteins:
        proteins.add("meat")

    flavors = set()
    for label, needles in FLAVOR_FAMILIES.items():
        if any(n in blob for n in needles):
            flavors.add(label)

    dish_family = "other"
    for label, needles in DISH_FAMILIES:
        if any(n in blob for n in needles):
            dish_family = label
            break

    tokens = {
        t
        for t in re.findall(r"[a-z]{3,}", recipe.name.casefold())
        if t not in {"the", "and", "with", "for", "from"}
    }
    overlap = set()
    for item in items:
        if item in PANTRY_STAPLES:
            continue
        for tok in re.findall(r"[a-z]{3,}", item):
            if tok in TOKEN_STOP or tok in PROTEIN_TOKENS:
                continue
            overlap.add(tok)
    return FlavorProfile(
        items=frozenset(items),
        proteins=frozenset(proteins),
        flavors=frozenset(flavors),
        dish_family=dish_family,
        name_tokens=frozenset(tokens),
        overlap_tokens=frozenset(overlap),
    )


def distinctive_items(profile: FlavorProfile) -> frozenset[str]:
    return frozenset(i for i in profile.items if i not in PANTRY_STAPLES)


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _idf_weights(profiles: list[FlavorProfile]) -> dict[str, float]:
    n = max(len(profiles), 1)
    df: Counter[str] = Counter()
    for p in profiles:
        df.update(p.overlap_tokens)
    return {item: math.log((n + 1) / (count + 1)) + 1.0 for item, count in df.items()}


def _weighted_overlap(items: set[str], pool: set[str], idf: dict[str, float]) -> float:
    if not items:
        return 0.0
    num = sum(idf.get(i, 1.0) for i in items & pool)
    den = sum(idf.get(i, 1.0) for i in items) or 1.0
    return num / den


def plan_week(
    store: RecipeStore,
    *,
    days: int = 7,
    servings: float = 4,
    start: date | None = None,
    diet: str | None = None,
    exclude: list[str] | None = None,
    include: list[str] | None = None,
    with_sides: bool = True,
    cooldown_days: int = 21,
    history: MealHistory | None = None,
    query: str = "",
    seed_limit: int = 800,
) -> MealPlan:
    """
    Build a week of meals that share shopping ingredients, vary flavors,
    and avoid repeating recent dishes.
    """
    start = start or date.today()
    banned = history.recent_ids(since=start, cooldown_days=cooldown_days) if history else set()

    mains_pool = _candidate_pool(
        store,
        course="main",
        diet=diet,
        exclude=exclude,
        include=include,
        query=query,
        limit=seed_limit,
        banned=banned,
    )
    if len(mains_pool) < days:
        # Fall back to unfiltered mains if the query was too tight.
        extra = _candidate_pool(
            store,
            course="main",
            diet=diet,
            exclude=exclude,
            include=include,
            query="",
            limit=seed_limit,
            banned=banned,
        )
        seen = {r.id for r in mains_pool}
        mains_pool.extend(r for r in extra if r.id not in seen)

    if not mains_pool:
        raise ValueError("No main-course recipes matched the filters.")

    profiles = {r.id: flavor_profile(r) for r in mains_pool}
    idf = _idf_weights(list(profiles.values()))
    partner_counts = _token_partner_counts(profiles)

    selected: list[Recipe] = []
    remaining = list(mains_pool)
    for _ in range(min(days, len(remaining))):
        pick = _pick_next(remaining, selected, profiles, idf, partner_counts)
        selected.append(pick)
        remaining = [r for r in remaining if r.id != pick.id]

    sides_pool: list[Recipe] = []
    if with_sides:
        sides_pool = _candidate_pool(
            store,
            course="side",
            diet=diet,
            exclude=exclude,
            include=None,
            query="",
            limit=seed_limit,
            banned=banned | {r.id for r in selected},
        )

    meals: list[PlannedMeal] = []
    used_side_ids: set[str] = set()
    for offset, main in enumerate(selected):
        when = start + timedelta(days=offset)
        scaled_main = scale_recipe(main, servings)
        factor = float(scaled_main.extras.get("scale_factor") or 1.0)
        meals.append(
            PlannedMeal(
                day=DAY_NAMES[when.weekday()],
                date=when.isoformat(),
                course="main",
                recipe=scaled_main,
                servings=servings,
                scale_factor=factor,
            )
        )
        if with_sides and sides_pool:
            side = _pick_side(
                sides_pool,
                main=main,
                used_ids=used_side_ids,
                profiles=profiles,
            )
            if side:
                used_side_ids.add(side.id)
                scaled_side = scale_recipe(side, servings)
                meals.append(
                    PlannedMeal(
                        day=DAY_NAMES[when.weekday()],
                        date=when.isoformat(),
                        course="side",
                        recipe=scaled_side,
                        servings=servings,
                        scale_factor=float(scaled_side.extras.get("scale_factor") or 1.0),
                    )
                )

    plan = MealPlan(
        start=start.isoformat(),
        days=len(selected),
        servings=servings,
        meals=meals,
        scores=_plan_scores(selected, profiles, idf),
    )
    return plan


def _candidate_pool(
    store: RecipeStore,
    *,
    course: str,
    diet: str | None,
    exclude: list[str] | None,
    include: list[str] | None,
    query: str,
    limit: int,
    banned: set[str],
) -> list[Recipe]:
    hits: list[Recipe] = []
    if query.strip():
        hits = store.search(
            query,
            limit=max(limit, 80),
            diet=diet,
            exclude=exclude,
            include=include,
            course=course,
        )
    if len(hits) < min(limit, 80) or not query.strip():
        for recipe in store.load_all():
            if recipe.id in banned:
                continue
            if not _passes_restrictions(
                recipe,
                include=include,
                exclude=exclude,
                diet=diet,
                course=course,
            ):
                continue
            hits.append(recipe)
            if query.strip() and len(hits) >= limit:
                break
    out = []
    seen: set[str] = set()
    for recipe in hits:
        if recipe.id in banned or recipe.id in seen:
            continue
        recipe.ensure_parsed()
        if len(recipe.parsed_ingredients) < 3:
            continue
        if course == "main" and not flavor_profile(recipe).overlap_tokens:
            continue
        if course == "main" and _looks_like_condiment(recipe):
            continue
        seen.add(recipe.id)
        out.append(recipe)
        if len(out) >= limit:
            break
    return out


def _looks_like_condiment(recipe: Recipe) -> bool:
    name = recipe.name.casefold()
    needles = (
        "pickle",
        "vinaigrette",
        "dressing",
        "marinade",
        "rub ",
        "seasoning",
        "syrup",
        "stock",
        "broth",
    )
    return any(n in name for n in needles)


def _token_partner_counts(profiles: dict[str, FlavorProfile]) -> dict[str, int]:
    inverted: dict[str, set[str]] = {}
    for rid, prof in profiles.items():
        for tok in prof.overlap_tokens:
            inverted.setdefault(tok, set()).add(rid)
    df = {tok: len(ids) for tok, ids in inverted.items()}
    counts: dict[str, int] = {}
    for rid, prof in profiles.items():
        score = 0.0
        for tok in prof.overlap_tokens:
            n = df.get(tok, 0)
            if 6 <= n <= max(len(profiles) // 3, 12):
                score += math.log(n)
        counts[rid] = int(score * 100)
    return counts


def _pick_next(
    remaining: list[Recipe],
    selected: list[Recipe],
    profiles: dict[str, FlavorProfile],
    idf: dict[str, float],
    partner_counts: dict[str, int],
) -> Recipe:
    if not selected:
        def opener(recipe: Recipe) -> tuple:
            prof = profiles[recipe.id]
            return (
                -partner_counts.get(recipe.id, 0),
                -len(prof.proteins),
                -len(prof.overlap_tokens),
            )

        return sorted(remaining, key=opener)[0]

    pool: set[str] = set()
    selected_profs = [profiles[r.id] for r in selected]
    for prof in selected_profs:
        pool |= set(prof.overlap_tokens)
    protein_counts = Counter(p for prof in selected_profs for p in prof.proteins)
    family_counts = Counter(prof.dish_family for prof in selected_profs)
    last = selected_profs[-1]

    best: Recipe | None = None
    best_score = -1e9
    for recipe in remaining:
        prof = profiles[recipe.id]
        items = set(prof.overlap_tokens)
        overlap = 0.5 * _jaccard(items, pool) + 0.5 * _weighted_overlap(items, pool, idf)
        flavor_sim = _jaccard(prof.flavors, last.flavors)
        name_sim = _jaccard(prof.name_tokens, last.name_tokens)
        week_flavor_sim = max((_jaccard(prof.flavors, s.flavors) for s in selected_profs), default=0.0)
        same_protein_adj = 1.0 if prof.proteins & last.proteins else 0.0
        same_family_adj = 1.0 if prof.dish_family == last.dish_family and prof.dish_family != "other" else 0.0
        protein_repeat = max((protein_counts[p] for p in prof.proteins), default=0)
        family_repeat = family_counts[prof.dish_family]
        variety = 1.0 - 0.5 * week_flavor_sim - 0.5 * flavor_sim

        score = (
            2.6 * overlap
            + 1.0 * variety
            - 2.8 * same_protein_adj
            - 2.5 * same_family_adj
            - 2.2 * name_sim
            - 0.6 * protein_repeat
            - 0.7 * family_repeat
        )
        if score > best_score:
            best_score = score
            best = recipe
    assert best is not None
    return best


def _pick_side(
    sides: list[Recipe],
    *,
    main: Recipe,
    used_ids: set[str],
    profiles: dict[str, FlavorProfile],
) -> Recipe | None:
    main_prof = profiles.get(main.id) or flavor_profile(main)
    main_items = set(distinctive_items(main_prof))
    best: Recipe | None = None
    best_score = -1e9
    for side in sides:
        if side.id in used_ids:
            continue
        prof = flavor_profile(side)
        items = set(distinctive_items(prof))
        overlap = _jaccard(items, main_items)
        too_close = _jaccard(prof.name_tokens, main_prof.name_tokens)
        score = 2.0 * overlap - 1.5 * too_close + 0.2 * min(len(items), 6)
        if score > best_score:
            best_score = score
            best = side
    return best


def _plan_scores(
    mains: list[Recipe],
    profiles: dict[str, FlavorProfile],
    idf: dict[str, float],
) -> dict[str, float]:
    profs = [profiles[r.id] for r in mains]
    item_sets = [set(p.overlap_tokens) for p in profs]
    union: set[str] = set()
    for s in item_sets:
        union |= s
    shared = set(item_sets[0]) if item_sets else set()
    for s in item_sets[1:]:
        shared &= s
    # Mean pairwise overlap of distinctive ingredients.
    pairwise = []
    for i, a in enumerate(item_sets):
        for b in item_sets[i + 1 :]:
            pairwise.append(_weighted_overlap(a, b, idf) if a else 0.0)
    flavor_pairs = []
    for i, a in enumerate(profs):
        for b in profs[i + 1 :]:
            flavor_pairs.append(_jaccard(a.flavors | a.proteins | {a.dish_family}, b.flavors | b.proteins | {b.dish_family}))
    adjacent_protein_repeats = 0
    for a, b in zip(profs, profs[1:]):
        if a.proteins & b.proteins:
            adjacent_protein_repeats += 1
    return {
        "ingredient_overlap": round(sum(pairwise) / len(pairwise), 3) if pairwise else 0.0,
        "flavor_diversity": round(1.0 - (sum(flavor_pairs) / len(flavor_pairs) if flavor_pairs else 0.0), 3),
        "unique_proteins": len({p for prof in profs for p in prof.proteins}),
        "adjacent_protein_repeats": adjacent_protein_repeats,
        "shopping_skus": len(union),
    }
