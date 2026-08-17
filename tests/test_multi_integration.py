from __future__ import annotations

from pathlib import Path

import pytest

from based_cooking.sources import discover_epubs, resolve_source

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_MIN = {
    "joy-of-cooking": 2200,
    "keep-it-simple": 60,
    "martha-one-pot": 100,
    "nigella-express": 160,
    "salt-fat-acid-heat": 95,
    "sheet-pan-suppers": 125,
    "food-lab": 220,
    "the-wok": 210,
}


@pytest.mark.integration
def test_all_epubs_resolve_and_extract_expected_counts() -> None:
    epubs = discover_epubs(ROOT)
    if len(epubs) < 8:
        pytest.skip("Not all cookbooks present")

    found: dict[str, int] = {}
    for epub in epubs:
        source = resolve_source(epub)
        recipes = source.extract()
        found[source.name] = len(recipes)
        assert recipes, f"No recipes from {epub.name}"
        with_ing = sum(1 for r in recipes if r.ingredients)
        assert with_ing / len(recipes) >= 0.95, f"{source.name} missing ingredients"

    for name, minimum in EXPECTED_MIN.items():
        assert name in found, f"Missing adapter results for {name}"
        assert found[name] >= minimum, f"{name}: {found[name]} < {minimum}"
