from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# Canonical cooking units we keep in the store.
CANONICAL_UNITS = {
    "tsp",
    "tbsp",
    "cup",
    "floz",
    "oz",
    "lb",
    "g",
    "kg",
    "ml",
    "l",
    "each",
    "clove",
    "slice",
    "can",
    "bunch",
    "stick",
    "head",
    "ear",
    "sprig",
    "leaf",
    "package",
}

# Vague amounts → approximate tsp (or to_taste when paired with seasonings).
VAGUE_TO_TSP = {
    "smidge": 1 / 16,
    "smidgen": 1 / 16,
    "pinch": 1 / 16,
    "pinches": 1 / 16,
    "dash": 1 / 8,
    "dashes": 1 / 8,
    "drop": 1 / 32,
    "drops": 1 / 32,
    "speck": 1 / 32,
    "touch": 1 / 16,
    "hint": 1 / 16,
}

UNIT_ALIASES: dict[str, str] = {
    "tsp": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "t": "tsp",
    "tsp.": "tsp",
    "tsps": "tsp",
    "tbsp": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tbsp.": "tbsp",
    "tbsps": "tbsp",
    "tbs": "tbsp",
    "T": "tbsp",
    "cup": "cup",
    "cups": "cup",
    "c": "cup",
    "c.": "cup",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "oz.": "oz",
    "ozs": "oz",
    "floz": "floz",
    "fluid ounce": "floz",
    "fluid ounces": "floz",
    "fl oz": "floz",
    "fl. oz": "floz",
    "fl. oz.": "floz",
    "lb": "lb",
    "pound": "lb",
    "pounds": "lb",
    "lb.": "lb",
    "lbs": "lb",
    "lbs.": "lb",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "g.": "g",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "kg.": "kg",
    "ml": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "ml.": "ml",
    "l": "l",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "l.": "l",
    "clove": "clove",
    "cloves": "clove",
    "slice": "slice",
    "slices": "slice",
    "can": "can",
    "cans": "can",
    "bunch": "bunch",
    "bunches": "bunch",
    "stick": "stick",
    "sticks": "stick",
    "head": "head",
    "heads": "head",
    "ear": "ear",
    "ears": "ear",
    "sprig": "sprig",
    "sprigs": "sprig",
    "leaf": "leaf",
    "leaves": "leaf",
    "package": "package",
    "packages": "package",
    "pkg": "package",
    "pkt": "package",
    "handful": "each",
    "handfuls": "each",
    "large handful": "each",
    "big handful": "each",
}

# Countable foods often written without a unit ("2 eggs", "1 onion").
COUNTABLE_ITEMS = {
    "egg",
    "eggs",
    "onion",
    "onions",
    "shallot",
    "shallots",
    "lemon",
    "lemons",
    "lime",
    "limes",
    "orange",
    "oranges",
    "apple",
    "apples",
    "banana",
    "bananas",
    "avocado",
    "avocados",
    "tomato",
    "tomatoes",
    "potato",
    "potatoes",
    "carrot",
    "carrots",
    "stalk",
    "stalks",
    "rib",
    "ribs",
    "bay leaf",
    "bay leaves",
    "garlic clove",
    "garlic cloves",
}

ITEM_ALIASES: dict[str, str] = {
    "eggs": "egg",
    "egg yolks": "egg yolk",
    "egg yolk": "egg yolk",
    "egg whites": "egg white",
    "egg white": "egg white",
    "onions": "onion",
    "yellow onion": "onion",
    "yellow onions": "onion",
    "white onion": "onion",
    "red onion": "red onion",
    "green onions": "scallion",
    "green onion": "scallion",
    "scallions": "scallion",
    "spring onions": "scallion",
    "kosher salt": "salt",
    "sea salt": "salt",
    "table salt": "salt",
    "fine salt": "salt",
    "unsalted butter": "butter",
    "salted butter": "butter",
    "sweet butter": "butter",
    "extra-virgin olive oil": "olive oil",
    "extra virgin olive oil": "olive oil",
    "evoo": "olive oil",
    "all-purpose flour": "flour",
    "all purpose flour": "flour",
    "ap flour": "flour",
    "granulated sugar": "sugar",
    "white sugar": "sugar",
    "black pepper": "pepper",
    "freshly ground black pepper": "pepper",
    "freshly ground pepper": "pepper",
    "ground black pepper": "pepper",
    "garlic cloves": "garlic",
    "garlic clove": "garlic",
    "cloves garlic": "garlic",
    "clove garlic": "garlic",
    "minced garlic": "garlic",
}

SEASONING_ITEMS = {
    "salt",
    "pepper",
    "black pepper",
    "cayenne",
    "paprika",
    "cinnamon",
    "nutmeg",
    "cumin",
    "oregano",
    "thyme",
    "rosemary",
    "chili flakes",
    "red pepper flakes",
}

PREP_WORDS = {
    "chopped",
    "diced",
    "minced",
    "sliced",
    "grated",
    "shredded",
    "melted",
    "softened",
    "room temperature",
    "divided",
    "drained",
    "rinsed",
    "peeled",
    "seeded",
    "trimmed",
    "crushed",
    "beaten",
    "whisked",
    "toasted",
    "cooked",
    "fresh",
    "dried",
    "frozen",
    "thawed",
    "whole",
    "halved",
    "quartered",
    "thinly",
    "finely",
    "roughly",
    "coarsely",
}

# Size words are kept out of prep noise for display ("2 large eggs" → "2 egg").
SIZE_WORDS = {"large", "medium", "small", "extra-large", "jumbo"}

FRACTIONS = {
    "¼": 0.25,
    "½": 0.5,
    "¾": 0.75,
    "⅓": 1 / 3,
    "⅔": 2 / 3,
    "⅛": 0.125,
    "⅜": 0.375,
    "⅝": 0.625,
    "⅞": 0.875,
    "⅕": 0.2,
    "⅖": 0.4,
    "⅗": 0.6,
    "⅘": 0.8,
    "⅙": 1 / 6,
    "⅚": 5 / 6,
}


@dataclass(slots=True)
class ParsedIngredient:
    """Structured ingredient line for search, nutrition, and LLM prompts."""

    raw: str
    quantity: float | None = None
    unit: str | None = None
    item: str = ""
    prep: str = ""
    to_taste: bool = False
    optional: bool = False
    allergens: list[str] = field(default_factory=list)
    notes: str = ""

    def display(self) -> str:
        """Human-useful form like '2 tbsp butter' or '1 onion'."""
        if self.to_taste and self.quantity is None:
            base = self.item or self.raw
            return f"{base} to taste".strip()
        parts: list[str] = []
        if self.quantity is not None:
            parts.append(_format_qty(self.quantity))
        if self.unit and self.unit != "each":
            parts.append(self.unit)
        if self.item:
            parts.append(self.item)
        elif self.raw:
            parts.append(self.raw)
        text = " ".join(parts).strip()
        if self.prep:
            text = f"{text}, {self.prep}"
        if self.to_taste and self.quantity is not None:
            text = f"{text} (to taste)"
        return text

    def scaled(self, factor: float) -> ParsedIngredient:
        """Return a copy with quantity multiplied. To-taste lines without a qty stay put."""
        qty = self.quantity
        if qty is not None and factor != 1:
            qty = qty * factor
        return ParsedIngredient(
            raw=self.raw,
            quantity=qty,
            unit=self.unit,
            item=self.item,
            prep=self.prep,
            to_taste=self.to_taste,
            optional=self.optional,
            allergens=list(self.allergens),
            notes=self.notes,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["display"] = self.display()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParsedIngredient:
        return cls(
            raw=data.get("raw", "") or "",
            quantity=data.get("quantity"),
            unit=data.get("unit"),
            item=data.get("item", "") or "",
            prep=data.get("prep", "") or "",
            to_taste=bool(data.get("to_taste")),
            optional=bool(data.get("optional")),
            allergens=list(data.get("allergens") or []),
            notes=data.get("notes", "") or "",
        )


def parse_ingredient(line: str) -> ParsedIngredient:
    """Parse one free-text ingredient line into qty / unit / item."""
    raw = _clean(line)
    if not raw:
        return ParsedIngredient(raw=line, item="")

    optional = bool(re.search(r"\boptional\b", raw, re.I)) or raw.startswith("(")
    to_taste = bool(re.search(r"\bto taste\b|\bas needed\b|\bfor serving\b", raw, re.I))

    working = raw.strip("()[] ")
    working = re.sub(r"\s+", " ", working)
    # Drop leading "TO SERVE WITH:" style labels
    working = re.sub(r"^(to serve with|serve with|for garnish|garnish)[:\s]+", "", working, flags=re.I)

    qty, rest = _split_quantity(working)
    vague_unit = None
    unit = None

    # Vague units like pinch / dash / smidge
    vague_match = re.match(
        r"(?:a\s+)?(smidge|smidgen|pinch|pinches|dash|dashes|drop|drops|speck|touch|hint)\s+(?:of\s+)?(.+)$",
        rest,
        flags=re.I,
    )
    if vague_match:
        vague_unit = vague_match.group(1).casefold()
        rest = vague_match.group(2).strip()
        qty = (qty or 1.0) * VAGUE_TO_TSP[vague_unit]
        unit = "tsp"
        # Seasonings left as small tsp amounts; still mark to_taste for salt/pepper-only lines.
        item_guess = _canonicalize_item(rest)
        if item_guess in SEASONING_ITEMS and vague_unit in {"smidge", "smidgen", "pinch", "touch", "hint"}:
            to_taste = True

    if unit is None:
        unit, rest = _split_unit(rest)

    # Countable foods: "2 large eggs" / "1 onion"
    item, prep = _split_item_prep(rest)
    item = _canonicalize_item(item)

    if unit is None and qty is not None and _looks_countable(item, rest):
        unit = "each"
        if item.endswith("s") and item not in {"asparagus", "molasses"} and qty == 1:
            # keep plural item as canonical singular when possible
            pass

    # "2 cloves garlic" already maps clove unit; item becomes garlic via aliases
    if unit == "clove" and item in {"", "garlic"}:
        item = "garlic"

    # Eggs without unit
    if unit is None and re.search(r"\beggs?\b", item, re.I):
        unit = "each"

    allergens = infer_allergens(item, raw)

    # If we only got noise, keep a cleaned item from raw
    if not item:
        item = _canonicalize_item(re.sub(r"^[\d./\s¼½¾⅓⅔⅛⅜⅝⅞]+", "", working).strip()) or working.casefold()

    notes = ""
    if vague_unit:
        notes = f"from_{vague_unit}"

    return ParsedIngredient(
        raw=raw,
        quantity=qty,
        unit=unit,
        item=item,
        prep=prep,
        to_taste=to_taste,
        optional=optional,
        allergens=allergens,
        notes=notes,
    )


def parse_ingredients(lines: list[str]) -> list[ParsedIngredient]:
    return [parse_ingredient(line) for line in lines if _clean(line)]


def infer_allergens(item: str, raw: str = "") -> list[str]:
    """Best-effort allergen tags from food name / raw line."""
    blob = f"{item} {raw}".casefold()
    found: list[str] = []

    rules: list[tuple[str, tuple[str, ...]]] = [
        ("dairy", ("milk", "cream", "butter", "cheese", "yogurt", "yoghurt", "whey", "buttermilk", "half-and-half", "sour cream", "mascarpone", "ricotta", "parmesan", "parm", "mozzarella", "cheddar", "ghee", "pecorino", "romano", "roquefort", "gorgonzola", "brie", "feta", "goat cheese", "cream cheese", "cotija", "gruyere", "gruyère", "swiss cheese", "provolone", "fontina", "asiago", "manchego", "blue cheese")),
        ("egg", ("egg", "eggs", "egg white", "egg yolk", "mayonnaise", "mayo")),
        ("gluten", ("flour", "wheat", "bread", "pasta", "noodle", "spaghetti", "couscous", "barley", "rye", "breadcrumb", "panko", "tortilla", "soy sauce", "worcestershire")),
        ("peanut", ("peanut", "peanuts", "peanut butter")),
        ("tree_nut", ("almond", "walnut", "pecan", "cashew", "pistachio", "hazelnut", "macadamia", "pine nut", "brazil nut")),
        ("soy", ("soy", "soya", "tofu", "tempeh", "edamame", "miso", "soy sauce")),
        ("fish", ("fish", "salmon", "tuna", "cod", "anchovy", "anchovies", "sardine", "trout", "halibut", "bass", "tilapia")),
        ("shellfish", ("shrimp", "prawn", "crab", "lobster", "clam", "mussel", "oyster", "scallop", "crawfish", "crayfish")),
        ("sesame", ("sesame", "tahini")),
        ("meat", ("beef", "pork", "lamb", "veal", "bacon", "ham", "sausage", "steak", "prosciutto", "pancetta", "chicken", "turkey", "duck", "hen", "meatball")),
        ("alcohol", ("wine", "beer", "rum", "vodka", "whiskey", "bourbon", "brandy", "sherry", "vermouth")),
        ("honey", ("honey",)),
    ]
    for allergen, needles in rules:
        if any(n in blob for n in needles):
            # Avoid "peanut" double-counting as tree_nut; peanut is separate.
            if allergen == "tree_nut" and "peanut" in blob:
                continue
            # "buttermilk" is dairy; "butter beans" false positive rare — accept.
            found.append(allergen)
    return found


def recipe_allergens(parsed: list[ParsedIngredient]) -> list[str]:
    seen: list[str] = []
    for ing in parsed:
        for a in ing.allergens:
            if a not in seen:
                seen.append(a)
    return seen


def matches_diet(allergens: list[str], diet: str) -> bool:
    """Return True if recipe allergens are compatible with a diet profile."""
    diet = diet.casefold().replace("-", "_").replace(" ", "_")
    blocked = {
        "vegetarian": {"meat", "fish", "shellfish"},
        "vegan": {"meat", "fish", "shellfish", "dairy", "egg", "honey"},
        "pescatarian": {"meat"},
        "dairy_free": {"dairy"},
        "gluten_free": {"gluten"},
        "nut_free": {"peanut", "tree_nut"},
        "peanut_free": {"peanut"},
        "egg_free": {"egg"},
        "soy_free": {"soy"},
        "shellfish_free": {"shellfish"},
    }.get(diet)
    if blocked is None:
        return True
    return not (set(allergens) & blocked)


def _split_quantity(text: str) -> tuple[float | None, str]:
    text = text.strip()
    # Patterns: 2, 2.5, 1/2, 1½, 1 1/2, 2-3 → take first number of range
    m = re.match(
        r"^(?P<q>(?:\d+\s+\d+/\d+)|(?:\d+/\d+)|(?:\d+[¼½¾⅓⅔⅛⅜⅝⅞⅕⅖⅗⅘⅙⅚])|(?:\d*\.?\d+)|(?:[¼½¾⅓⅔⅛⅜⅝⅞⅕⅖⅗⅘⅙⅚]))"
        r"(?:\s*[-–—to]+\s*(?:\d+\s+\d+/\d+|\d+/\d+|\d*\.?\d+|[¼½¾⅓⅔⅛⅜⅝⅞]))?"
        r"(?P<rest>\s+.*)?$",
        text,
        flags=re.I,
    )
    if not m:
        # "a cup of …" / "an onion"
        if re.match(r"^(?:a|an)\s+", text, re.I):
            return 1.0, re.sub(r"^(?:a|an)\s+", "", text, flags=re.I)
        return None, text
    qty = _parse_number(m.group("q"))
    rest = (m.group("rest") or "").strip()
    return qty, rest


def _parse_number(token: str) -> float:
    token = token.strip()
    # mixed unicode: 1½
    for glyph, value in FRACTIONS.items():
        if glyph in token:
            left = token.replace(glyph, "").strip()
            return (float(left) if left else 0.0) + value
    if re.fullmatch(r"\d+\s+\d+/\d+", token):
        whole, frac = token.split()
        num, den = frac.split("/")
        return float(whole) + float(num) / float(den)
    if "/" in token:
        num, den = token.split("/", 1)
        return float(num) / float(den)
    return float(token)


def _split_unit(text: str) -> tuple[str | None, str]:
    text = text.strip()
    if not text:
        return None, text
    # Prefer longer aliases first
    lower = text.casefold()
    for alias in sorted(UNIT_ALIASES.keys(), key=len, reverse=True):
        alias_l = alias.casefold()
        if lower.startswith(alias_l + " ") or lower == alias_l:
            unit = UNIT_ALIASES[alias]
            rest = text[len(alias_l) :].strip(" .")
            rest = re.sub(r"^of\s+", "", rest, flags=re.I)
            return unit, rest
    return None, text


def _split_item_prep(text: str) -> tuple[str, str]:
    text = text.strip().strip(",")
    # Split on comma prep: "butter, melted"
    prep = ""
    if "," in text:
        main, _, tail = text.partition(",")
        # Keep parenthetical alternatives in main when possible
        if not main.strip().startswith("("):
            text = main.strip()
            prep = _clean_prep(tail)

    # Strip trailing prep adjectives that are clearly prep
    tokens = text.split()
    leading_prep: list[str] = []
    while tokens:
        word = tokens[0].casefold().strip(",")
        if word in SIZE_WORDS:
            tokens.pop(0)
            continue
        if word in PREP_WORDS:
            leading_prep.append(word)
            tokens.pop(0)
            continue
        break
    trailing_prep: list[str] = []
    while tokens:
        word = tokens[-1].casefold().strip(",")
        if word in SIZE_WORDS:
            tokens.pop()
            continue
        if word in PREP_WORDS:
            trailing_prep.insert(0, word)
            tokens.pop()
            continue
        break

    item = " ".join(tokens).strip(" ,.")
    # Remove simple trailing parenthetical notes from item for matching
    item = re.sub(r"\s*\([^)]*\)\s*$", "", item).strip()
    # Cut at "or" alternatives for canonical item: keep first option
    if re.search(r"\bor\b", item, re.I):
        item = re.split(r"\bor\b", item, maxsplit=1, flags=re.I)[0].strip(" ,/")

    merged_prep = ", ".join(p for p in [" ".join(leading_prep), prep, " ".join(trailing_prep)] if p)
    return item.casefold(), merged_prep


def _clean_prep(text: str) -> str:
    text = _clean(text).strip(" ,.")
    # Drop "or to taste" style tails already handled
    text = re.sub(r"\bor to taste\b", "", text, flags=re.I).strip(" ,.")
    return text.casefold()


def _canonicalize_item(item: str) -> str:
    item = _clean(item).casefold().strip(" .,;")
    item = re.sub(r"^(fresh|dried|frozen|ground|whole)\s+", "", item)
    if item in ITEM_ALIASES:
        return ITEM_ALIASES[item]
    # Try without leading size words already stripped
    for alias, canon in ITEM_ALIASES.items():
        if item == alias or item.endswith(" " + alias):
            return canon
    # Singular-ish: eggs -> egg when exact
    if item.endswith("oes") and item[:-2] in COUNTABLE_ITEMS:
        return item[:-2]
    if item.endswith("s") and item[:-1] in {c.rstrip("s") if c.endswith("s") else c for c in COUNTABLE_ITEMS}:
        singular = item[:-1]
        return ITEM_ALIASES.get(singular, singular)
    return item


def _looks_countable(item: str, rest: str) -> bool:
    blob = f"{item} {rest}".casefold()
    if item in COUNTABLE_ITEMS or item.rstrip("s") in {c.rstrip("s") for c in COUNTABLE_ITEMS}:
        return True
    return any(c in blob.split() for c in ("egg", "eggs", "onion", "onions", "lemon", "lime"))


def format_qty(value: float) -> str:
    """Pretty-print a cooking quantity (1, 1/2, 1 1/2, …)."""
    return _format_qty(value)


def _format_qty(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    # common cooking fractions
    table = {
        0.125: "1/8",
        0.25: "1/4",
        0.333: "1/3",
        1 / 3: "1/3",
        0.375: "3/8",
        0.5: "1/2",
        0.625: "5/8",
        0.666: "2/3",
        2 / 3: "2/3",
        0.75: "3/4",
        0.875: "7/8",
        1 / 16: "1/16",
        1 / 8: "1/8",
    }
    for target, label in table.items():
        if abs(value - target) < 0.02:
            return label
    # mixed numbers
    whole = int(value)
    frac = value - whole
    if whole and frac > 0.05:
        return f"{whole} {_format_qty(frac)}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _clean(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text
