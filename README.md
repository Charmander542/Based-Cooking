# Based Cooking

Scrape cookbooks into a **quickly searchable** recipe store for LLM dinner planning.

## Supported cookbooks

| Book | Adapter | Typical yield |
|------|---------|---------------|
| Joy of Cooking | `joy-of-cooking` | ~2294 |
| Keep It Simple, Y'all | `keep-it-simple` | ~62 |
| Martha Stewart One Pot | `martha-one-pot` | ~103 |
| Nigella Express | `nigella-express` | ~165 |
| Salt, Fat, Acid, Heat | `salt-fat-acid-heat` | ~99 |
| Sheet Pan Suppers | `sheet-pan-suppers` | ~129 |
| The Food Lab | `food-lab` | ~246 |
| The Wok | `the-wok` | ~221 |
| [based.cooking](https://based.cooking/) (web) | `based-cooking-web` | ~349 |
| Food Network Magazine 1,000 Easy Recipes | `food-network-magazine` | ~895 (+ Food Network URLs) |

Each recipe is normalized to: name, description, yield, ingredients, steps, page, chapter, source, **url** (for web recipes).

Stored as:

- `data/recipes.jsonl` — one recipe per line (easy to stream into an LLM)
- `data/recipes.sqlite3` — SQLite FTS5 for fast keyword search

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Scrape everything

```powershell
based-cooking scrape-all . --data-dir data
based-cooking scrape "https://based.cooking/" --data-dir data
based-cooking scrape "Food Network Magazine ....epub" --data-dir data --match-foodnetwork
based-cooking stats --data-dir data
based-cooking search "chicken mushrooms weeknight" --limit 8
based-cooking context "easy sheet-pan dinner" --limit 6
```

Scrape one book (merges into the store by source):

```powershell
based-cooking scrape "The Food Lab (...).epub" --data-dir data
```

## Tests

```powershell
pytest                     # unit + fixtures
pytest -m integration      # full EPUB extraction checks
```

## Adding another cookbook

1. Drop the `.epub` in the folder.
2. Probe its XHTML for recipe title / ingredient / step CSS classes.
3. Add `src/based_cooking/sources/<book>.py` subclassing `EpubCookbookSource`.
4. Register a title fingerprint in `sources/base.py` `_TITLE_ADAPTERS`.
5. Add a fixture + unit test under `tests/fixtures/multi/`.

Generic EPUB heuristic remains the fallback when no adapter matches.

## Website scraping (later)

`WebRecipeSource` is stubbed. Add site adapters and wire them in `resolve_source()` for `http(s)://` URLs.

## Notes

Use only cookbooks / sites you have rights to use. Scraped text is for personal local tooling.
