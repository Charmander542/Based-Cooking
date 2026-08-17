from __future__ import annotations

import re

from based_cooking.models import Recipe

# Stable course labels used for filtering / LLM meal planning.
COURSES = (
    "main",
    "side",
    "appetizer",
    "dessert",
    "breakfast",
    "drink",
    "sauce",
    "bread",
    "staple",
    "other",
)

# Chapter / section cues (substring match, casefolded).
_CHAPTER_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "dessert",
        (
            "cake",
            "cookie",
            "dessert",
            "pie",
            "pastr",
            "icing",
            "frosting",
            "ice cream",
            "candy",
            "confection",
            "sweet sauce",
        ),
    ),
    (
        "drink",
        ("cocktail", "beverage", "wine", "beer", "drink"),
    ),
    (
        "sauce",
        (
            "sauce",
            "dressing",
            "marinade",
            "seasoning",
            "condiment",
        ),
    ),
    (
        "staple",
        ("stock", "broth", "basic", "pantry"),
    ),
    (
        "appetizer",
        ("appetizer", "hors d", "starter", "snack", "dip"),
    ),
    (
        "bread",
        ("bread", "biscuit", "muffin", "roll"),
    ),
    (
        "breakfast",
        ("pancake", "waffle", "doughnut", "breakfast", "brunch", "egg dish"),
    ),
    (
        "side",
        (
            "vegetable",
            "salad",
            "grain",
            "side",
            "potato",
            "fruit",
        ),
    ),
    (
        "main",
        (
            "meat",
            "poultry",
            "wildfowl",
            "fish",
            "shellfish",
            "pasta",
            "noodle",
            "dumpling",
            "one pot",
            "wok",
            "supper",
            "dinner",
            "entree",
            "entrée",
        ),
    ),
]

_NAME_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "dessert",
        (
            "cake",
            "cookie",
            "brownie",
            "pie",
            "tart",
            "pudding",
            "ice cream",
            "sorbet",
            "candy",
            "fudge",
            "cupcake",
            "cheesecake",
            "mousse",
            "parfait",
            "cobbler",
            "crumble",
            "whoopie",
            "macaron",
            "truffle",
        ),
    ),
    (
        "drink",
        (
            "smoothie",
            "cocktail",
            "martini",
            "margarita",
            "lemonade",
            "sangria",
            "punch",
            "spritz",
            "milkshake",
            "latte",
            "coffee",
            "tea ",
            "hot chocolate",
            "mimosa",
        ),
    ),
    (
        "sauce",
        (
            "sauce",
            "dressing",
            "vinaigrette",
            "marinade",
            "rub ",
            "pesto",
            "aioli",
            "mayo",
            "gravy",
            "salsa",
            "chutney",
            "relish",
            "jam",
            "jelly",
            "syrup",
            "glaze",
        ),
    ),
    (
        "staple",
        ("stock", "broth", "bouillon", "simple syrup"),
    ),
    (
        "appetizer",
        (
            "dip",
            "crostini",
            "bruschetta",
            "nacho",
            "wing",
            "deviled",
            "canape",
            "canapé",
            "finger food",
            "tea sandwich",
            "potato skin",
            "party mix",
            "hummus",
            "guacamole",
        ),
    ),
    (
        "bread",
        ("bread", "biscuit", "muffin", "scone", "focaccia", "bagel", "loaf", "cornbread"),
    ),
    (
        "breakfast",
        (
            "pancake",
            "waffle",
            "french toast",
            "omelet",
            "omelette",
            "frittata",
            "scramble",
            "granola",
            "porridge",
            "oatmeal",
            "breakfast",
        ),
    ),
    (
        "side",
        (
            "salad",
            "slaw",
            "coleslaw",
            "side",
            "mashed potato",
            "roast potato",
            "rice pilaf",
            "risotto",  # often side/main — treat as side unless protein-heavy below
            "beans",
            "greens",
            "vegetable",
        ),
    ),
    (
        "main",
        (
            "roast",
            "steak",
            "burger",
            "lasagna",
            "lasagne",
            "casserole",
            "paella",
            "curry",
            "stew",
            "chili",
            "chilli",
            "pizza",
            "taco",
            "burrito",
            "enchilada",
            "kebab",
            "meatball",
            "meat loaf",
            "meatloaf",
            "chicken",
            "turkey",
            "pork",
            "beef",
            "lamb",
            "salmon",
            "shrimp",
            "pasta",
            "spaghetti",
            "noodle",
            "ramen",
            "soup",
            "chowder",
            "gumbo",
            "risotto",
            "bowl",
        ),
    ),
]

_PROTEIN_ITEMS = {
    "chicken",
    "turkey",
    "duck",
    "beef",
    "pork",
    "lamb",
    "veal",
    "bacon",
    "ham",
    "sausage",
    "steak",
    "salmon",
    "tuna",
    "shrimp",
    "prawn",
    "crab",
    "lobster",
    "fish",
    "tofu",
    "tempeh",
}


def infer_course(recipe: Recipe) -> str:
    """Heuristic course label: main, side, dessert, etc."""
    chapter = f"{recipe.chapter} {recipe.section}".casefold()
    name = recipe.name.casefold()
    tags = {t.casefold() for t in recipe.tags}
    blob = f"{name} {chapter} {' '.join(tags)}"

    # Explicit existing tags win when already course-like.
    for course in COURSES:
        if course in tags and course != "other":
            # "side" tag from sites is trusted; "sauce"/"dessert" too.
            if course in {"main", "side", "dessert", "appetizer", "breakfast", "drink", "sauce", "bread"}:
                return course

    for course, needles in _CHAPTER_RULES:
        if any(n in chapter for n in needles):
            # Joy VEGETABLES / SALADS are sides unless the dish is clearly a meal.
            if course == "side" and _looks_like_main(recipe, blob):
                return "main"
            if course == "breakfast" and _looks_like_main(recipe, blob) and "egg" not in chapter:
                return "main"
            return course

    for course, needles in _NAME_RULES:
        if any(n in name for n in needles):
            if course == "side" and _looks_like_main(recipe, blob):
                return "main"
            if course == "main" and _looks_like_side_only(name, chapter):
                return "side"
            return course

    if _looks_like_main(recipe, blob):
        return "main"
    if _looks_like_side_only(name, chapter):
        return "side"
    if len(recipe.ingredients) <= 4 and not _has_protein(recipe):
        return "side"
    return "other"


def apply_course(recipe: Recipe) -> Recipe:
    """Set recipe.course and ensure a matching course tag."""
    course = infer_course(recipe)
    recipe.course = course
    tags = [t for t in recipe.tags if t.casefold() not in COURSES]
    tags.append(course)
    recipe.tags = tags
    return recipe


def _looks_like_main(recipe: Recipe, blob: str) -> bool:
    if any(x in blob for x in ("entree", "entrée", "dinner", "supper", "one pot", "sheet pan")):
        return True
    if _has_protein(recipe):
        # Protein + pasta/rice/potato often means a plate, not a side.
        if any(x in blob for x in ("pasta", "noodle", "rice", "bowl", "taco", "burger", "pizza", "stew", "soup", "curry")):
            return True
        # Substantial protein amount cues
        for ing in recipe.parsed_ingredients or []:
            item = (ing.item or "").casefold()
            if any(p in item for p in _PROTEIN_ITEMS):
                qty = ing.quantity or 0
                unit = ing.unit or ""
                if unit in {"lb", "kg"} and qty >= 0.5:
                    return True
                if unit == "oz" and qty >= 8:
                    return True
                if unit == "each" and qty >= 2 and any(p in item for p in ("chicken", "breast", "thigh", "steak")):
                    return True
        # Any meat/fish allergen with enough ingredients → likely a main.
        if set(a.casefold() for a in recipe.allergens) & {"meat", "fish", "shellfish"}:
            if len(recipe.ingredients) >= 5:
                return True
    return False


def _looks_like_side_only(name: str, chapter: str) -> bool:
    side_name = (
        "salad",
        "slaw",
        "vegetables",
        "greens",
        "mashed",
        "roasted vegetables",
        "beans",
        "rice",
        "pilaf",
        "polenta",
        "grits",
    )
    if any(s in name for s in side_name) and not re.search(
        r"\b(chicken|beef|pork|shrimp|salmon|tuna|turkey|lamb)\b", name
    ):
        return True
    if "vegetable" in chapter or "salad" in chapter:
        return True
    return False


def _has_protein(recipe: Recipe) -> bool:
    if set(a.casefold() for a in recipe.allergens) & {"meat", "fish", "shellfish"}:
        return True
    parts = [
        *(recipe.ingredients),
        *((p.item for p in recipe.parsed_ingredients) if recipe.parsed_ingredients else ()),
        recipe.name,
    ]
    blob = " ".join(parts).casefold()
    return any(p in blob for p in _PROTEIN_ITEMS)
