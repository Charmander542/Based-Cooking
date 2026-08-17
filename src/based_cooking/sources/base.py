from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from based_cooking.models import Recipe


class RecipeSource(ABC):
    """Pluggable source: EPUB cookbooks today, websites later."""

    name: str

    @abstractmethod
    def iter_recipes(self) -> Iterator[Recipe]:
        raise NotImplementedError

    def extract(self) -> list[Recipe]:
        return list(self.iter_recipes())


class WebRecipeSource(RecipeSource):
    """Placeholder for future website scraping adapters."""

    name = "web"

    def __init__(self, urls: list[str] | None = None) -> None:
        self.urls = urls or []

    def iter_recipes(self) -> Iterator[Recipe]:
        raise NotImplementedError(
            "Website scraping is intentionally stubbed. "
            "Add a site-specific adapter under based_cooking.sources.web."
        )


# (title substring, factory) — first match wins
_TITLE_ADAPTERS: list[tuple[str, str]] = [
    ("joy of cooking", "based_cooking.sources.joy_of_cooking:JoyOfCookingSource"),
    ("keep it simple", "based_cooking.sources.keep_it_simple:KeepItSimpleSource"),
    ("one pot", "based_cooking.sources.martha:MarthaOnePotSource"),
    ("nigella express", "based_cooking.sources.nigella:NigellaExpressSource"),
    ("salt, fat, acid, heat", "based_cooking.sources.sfah:SaltFatAcidHeatSource"),
    ("sheet pan suppers", "based_cooking.sources.sheet_pan:SheetPanSuppersSource"),
    ("food lab", "based_cooking.sources.food_lab:FoodLabSource"),
    ("wok", "based_cooking.sources.wok:WokSource"),
    ("food network magazine", "based_cooking.sources.food_network_mag:FoodNetworkMagazineSource"),
    ("1000 easy recipes", "based_cooking.sources.food_network_mag:FoodNetworkMagazineSource"),
    ("1,000 easy recipes", "based_cooking.sources.food_network_mag:FoodNetworkMagazineSource"),
]


def _load_adapter(dotted: str):
    module_name, class_name = dotted.split(":")
    import importlib

    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def resolve_source(path_or_url: str | Path):
    """Factory that picks an EPUB cookbook or website adapter."""
    from based_cooking.sources.epub import EpubCookbookSource

    text = str(path_or_url)
    if text.startswith(("http://", "https://")):
        if "based.cooking" in text.lower():
            from based_cooking.sources.based_cooking_web import BasedCookingWebSource

            return BasedCookingWebSource(text)
        return WebRecipeSource([text])

    path = Path(path_or_url)
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix.lower() == ".epub":
        probe = EpubCookbookSource(path)
        meta = probe.metadata()
        title = (meta.get("title") or "").lower()
        filename = path.name.lower()
        blob = f"{title} {filename}"
        for needle, dotted in _TITLE_ADAPTERS:
            if needle in blob:
                cls = _load_adapter(dotted)
                return cls(path)
        return probe

    raise ValueError(f"Unsupported source: {path}")


def discover_epubs(directory: str | Path) -> list[Path]:
    root = Path(directory)
    return sorted(root.glob("*.epub"), key=lambda p: p.name.lower())
