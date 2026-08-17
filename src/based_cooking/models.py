from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from based_cooking.ingredients import ParsedIngredient


@dataclass(slots=True)
class RecipeStep:
    """One instructional beat, optionally introducing ingredients (Joy-style interleaving)."""

    text: str
    ingredients: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "ingredients": list(self.ingredients)}


@dataclass(slots=True)
class Recipe:
    """Normalized recipe used by all sources and the searchable store."""

    id: str
    name: str
    source: str
    source_id: str
    ingredients: list[str]
    steps: list[RecipeStep]
    description: str = ""
    yield_text: str = ""
    page: int | None = None
    chapter: str = ""
    section: str = ""
    tags: list[str] = field(default_factory=list)
    url: str = ""
    extras: dict[str, Any] = field(default_factory=dict)
    # Structured companion fields (filled by `normalize` / scrape post-process).
    parsed_ingredients: list[ParsedIngredient] = field(default_factory=list)
    allergens: list[str] = field(default_factory=list)
    course: str = ""  # main | side | appetizer | dessert | breakfast | drink | sauce | bread | staple | other

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [step.to_dict() for step in self.steps]
        data["parsed_ingredients"] = [p.to_dict() for p in self.parsed_ingredients]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Recipe:
        steps_raw = data.get("steps") or []
        steps = [
            RecipeStep(
                text=item.get("text", "") if isinstance(item, dict) else str(item),
                ingredients=list(item.get("ingredients") or [])
                if isinstance(item, dict)
                else [],
            )
            for item in steps_raw
        ]
        parsed_raw = data.get("parsed_ingredients") or []
        parsed = [
            ParsedIngredient.from_dict(item) if isinstance(item, dict) else ParsedIngredient(raw=str(item))
            for item in parsed_raw
        ]
        return cls(
            id=data["id"],
            name=data["name"],
            source=data.get("source", ""),
            source_id=data.get("source_id", ""),
            ingredients=list(data.get("ingredients") or []),
            steps=steps,
            description=data.get("description", "") or "",
            yield_text=data.get("yield_text", "") or "",
            page=data.get("page"),
            chapter=data.get("chapter", "") or "",
            section=data.get("section", "") or "",
            tags=list(data.get("tags") or []),
            url=data.get("url", "") or "",
            extras=dict(data.get("extras") or {}),
            parsed_ingredients=parsed,
            allergens=list(data.get("allergens") or []),
            course=data.get("course", "") or "",
        )

    def search_blob(self) -> str:
        """Flattened text used for FTS / LLM retrieval."""
        parts = [
            self.name,
            self.description,
            self.yield_text,
            self.chapter,
            self.section,
            self.course,
            " ".join(self.tags),
            " ".join(self.allergens),
            " ".join(self.ingredients),
            " ".join(p.display() for p in self.parsed_ingredients),
            self.url,
        ]
        for step in self.steps:
            parts.append(step.text)
            parts.extend(step.ingredients)
        if self.page is not None:
            parts.append(f"page {self.page}")
        return "\n".join(p for p in parts if p)

    def ensure_parsed(self) -> Recipe:
        """Fill parsed_ingredients / allergens / course from raw lines if missing."""
        from based_cooking.course import apply_course
        from based_cooking.ingredients import parse_ingredients, recipe_allergens

        if not self.parsed_ingredients and self.ingredients:
            self.parsed_ingredients = parse_ingredients(self.ingredients)
        if not self.allergens and self.parsed_ingredients:
            self.allergens = recipe_allergens(self.parsed_ingredients)
        if not self.course:
            apply_course(self)
        return self
