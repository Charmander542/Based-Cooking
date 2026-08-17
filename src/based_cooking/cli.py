from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from based_cooking.sources import discover_epubs, resolve_source
from based_cooking.store import RecipeStore


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="based-cooking",
        description="Scrape cookbooks into a searchable recipe store for LLM meal planning.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scrape = sub.add_parser("scrape", help="Extract recipes from an EPUB (or future web URL)")
    scrape.add_argument("source", help="Path to .epub (or https:// URL later)")
    scrape.add_argument(
        "--data-dir",
        default="data",
        help="Output directory for recipes.jsonl and recipes.sqlite3",
    )
    scrape.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max recipes to extract (0 = all)",
    )
    scrape.add_argument(
        "--replace-all",
        action="store_true",
        help="Wipe the store and write only this source (default merges by source)",
    )
    scrape.add_argument(
        "--delay",
        type=float,
        default=0.15,
        help="Delay between web page fetches in seconds (web sources only)",
    )
    scrape.add_argument(
        "--match-foodnetwork",
        action="store_true",
        help="After scraping Food Network Magazine, search foodnetwork.com for matching recipe URLs",
    )
    scrape.add_argument(
        "--match-limit",
        type=int,
        default=0,
        help="Optional cap on Food Network URL matches (0 = all recipes)",
    )

    scrape_all = sub.add_parser(
        "scrape-all",
        help="Scrape every .epub in a directory into one merged store",
    )
    scrape_all.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory containing .epub files (default: current dir)",
    )
    scrape_all.add_argument("--data-dir", default="data")

    search = sub.add_parser("search", help="Full-text search the recipe store")
    search.add_argument(
        "query",
        nargs="?",
        default="",
        help="Free-text query (optional if --include is set)",
    )
    search.add_argument("--data-dir", default="data")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--chapter")
    search.add_argument("--source", help="Filter by source id, e.g. food-lab")
    search.add_argument(
        "--include",
        default="",
        help="Comma-separated ingredients that must all appear (tomato,garlic)",
    )
    search.add_argument(
        "--exclude",
        default="",
        help="Comma-separated allergens/ingredients to exclude (peanut,dairy,cilantro)",
    )
    search.add_argument(
        "--diet",
        default="",
        help="Diet profile: vegetarian, vegan, gluten_free, dairy_free, nut_free, ...",
    )
    search.add_argument(
        "--course",
        default="",
        help="Course: main, side, appetizer, dessert, breakfast, drink, sauce, bread, staple",
    )
    search.add_argument("--json", action="store_true")

    show = sub.add_parser("show", help="Show one recipe by id")
    show.add_argument("recipe_id")
    show.add_argument("--data-dir", default="data")
    show.add_argument(
        "--nutrition",
        action="store_true",
        help="Include estimated nutrition from the companion ingredient DB",
    )

    stats = sub.add_parser("stats", help="Summarize the recipe store")
    stats.add_argument("--data-dir", default="data")

    normalize = sub.add_parser(
        "normalize",
        help="Parse all ingredient lines into qty/unit/item + allergen tags",
    )
    normalize.add_argument("--data-dir", default="data")

    context = sub.add_parser(
        "context",
        help="Emit compact JSON for an LLM dinner prompt",
    )
    context.add_argument("query", help="Natural-language dinner request")
    context.add_argument("--data-dir", default="data")
    context.add_argument("--limit", type=int, default=8)
    context.add_argument(
        "--include",
        default="",
        help="Comma-separated ingredients that must all appear",
    )
    context.add_argument(
        "--exclude",
        default="",
        help="Comma-separated allergens/ingredients to exclude",
    )
    context.add_argument("--diet", default="", help="Diet profile filter")
    context.add_argument(
        "--course",
        default="",
        help="Course: main, side, appetizer, dessert, ...",
    )
    context.add_argument(
        "--nutrition",
        action="store_true",
        help="Attach estimated nutrition totals when ingredients match the DB",
    )

    scale = sub.add_parser("scale", help="Scale one recipe to a target serving count")
    scale.add_argument("recipe_id")
    scale.add_argument("--servings", type=float, required=True, help="Target number of servings")
    scale.add_argument("--data-dir", default="data")

    plan = sub.add_parser(
        "plan",
        help="Build a week of meals with shared ingredients, flavor variety, and no close repeats",
    )
    plan.add_argument("--data-dir", default="data")
    plan.add_argument("--days", type=int, default=7)
    plan.add_argument("--servings", type=float, default=4)
    plan.add_argument("--start", default="", help="Start date YYYY-MM-DD (default: today)")
    plan.add_argument("--query", default="", help="Optional vibe / keyword seed (e.g. chicken)")
    plan.add_argument("--include", default="", help="Required ingredients, comma-separated")
    plan.add_argument("--exclude", default="", help="Allergens/ingredients to exclude")
    plan.add_argument("--diet", default="")
    plan.add_argument("--no-sides", action="store_true", help="Mains only")
    plan.add_argument(
        "--cooldown",
        type=int,
        default=21,
        help="Days to avoid repeating a recipe (uses meal_history.jsonl)",
    )
    plan.add_argument(
        "--save",
        action="store_true",
        help="Append this plan to data/meal_history.jsonl so later weeks skip these dishes",
    )
    plan.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "scrape":
        return cmd_scrape(args)
    if args.command == "scrape-all":
        return cmd_scrape_all(args)
    if args.command == "search":
        return cmd_search(args)
    if args.command == "show":
        return cmd_show(args)
    if args.command == "stats":
        return cmd_stats(args)
    if args.command == "normalize":
        return cmd_normalize(args)
    if args.command == "context":
        return cmd_context(args)
    if args.command == "scale":
        return cmd_scale(args)
    if args.command == "plan":
        return cmd_plan(args)
    return 1


def _parse_csv(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def cmd_scrape(args: argparse.Namespace) -> int:
    source = resolve_source(args.source)
    if hasattr(source, "delay_seconds"):
        source.delay_seconds = max(0.0, float(args.delay))
    if args.limit and args.limit > 0 and hasattr(source, "limit"):
        source.limit = args.limit
    recipes = source.extract()
    if args.limit and args.limit > 0 and not hasattr(source, "limit"):
        recipes = recipes[: args.limit]

    if args.match_foodnetwork or source.name == "food-network-magazine":
        # Default-on for FN magazine when flag set; also allow explicit flag for safety.
        if args.match_foodnetwork:
            from based_cooking.sources.food_network_mag import attach_foodnetwork_urls

            print(
                f"Matching Food Network URLs for {len(recipes) if not args.match_limit else min(len(recipes), args.match_limit)} recipes..."
            )
            attach_foodnetwork_urls(
                recipes,
                delay_seconds=max(0.15, float(args.delay)),
                limit=args.match_limit,
            )

    store = RecipeStore(args.data_dir)
    if args.replace_all:
        store.replace_all(recipes)
        total = len(recipes)
    else:
        merged = store.upsert_source(source.name, recipes)
        total = len(merged)
    print(f"Extracted {len(recipes)} recipes via {source.name}")
    with_url = sum(1 for r in recipes if r.url)
    if with_url:
        print(f"With recipe links: {with_url}")
    print(f"Store now has {total} recipes")
    print(f"Wrote {store.jsonl_path}")
    print(f"Wrote {store.db_path}")
    return 0


def cmd_scrape_all(args: argparse.Namespace) -> int:
    epubs = discover_epubs(args.directory)
    if not epubs:
        print(f"No .epub files found in {args.directory}", file=sys.stderr)
        return 1
    store = RecipeStore(args.data_dir)
    grand_total = 0
    for epub in epubs:
        source = resolve_source(epub)
        recipes = source.extract()
        store.upsert_source(source.name, recipes)
        print(f"{epub.name}: {len(recipes)} via {source.name}")
        grand_total += len(recipes)
    print(f"Total extracted this run: {grand_total}")
    print(f"Store size: {len(store.load_all())}")
    print(f"Wrote {store.jsonl_path}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    include = _parse_csv(args.include)
    course = (args.course or "").strip()
    if not (args.query or "").strip() and not include and not course:
        print("Provide a query, --include, and/or --course.", file=sys.stderr)
        return 1
    store = RecipeStore(args.data_dir)
    hits = store.search(
        args.query,
        limit=args.limit,
        chapter=args.chapter,
        source=args.source,
        include=include,
        exclude=_parse_csv(args.exclude),
        diet=args.diet or None,
        course=course or None,
    )
    if args.json:
        print(json.dumps([r.to_dict() for r in hits], ensure_ascii=False, indent=2))
        return 0
    if not hits:
        print("No matches.")
        return 0
    for recipe in hits:
        page = f"p.{recipe.page}" if recipe.page is not None else "p.?"
        print(f"- {recipe.name} ({page}) [{recipe.source}] [{recipe.id}]")
        if recipe.course:
            print(f"  course: {recipe.course}")
        if recipe.url:
            print(f"  {recipe.url}")
        if recipe.allergens:
            print(f"  allergens: {', '.join(recipe.allergens)}")
        if recipe.parsed_ingredients:
            preview = ", ".join(p.display() for p in recipe.parsed_ingredients[:5])
            more = "…" if len(recipe.parsed_ingredients) > 5 else ""
            print(f"  normalized: {preview}{more}")
        elif recipe.description:
            print(
                f"  {recipe.description[:140]}"
                f"{'…' if len(recipe.description) > 140 else ''}"
            )
        print(f"  ingredients: {len(recipe.ingredients)} | steps: {len(recipe.steps)}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    store = RecipeStore(args.data_dir)
    recipe = store.get(args.recipe_id)
    if recipe is None:
        print(f"Not found: {args.recipe_id}", file=sys.stderr)
        return 1
    recipe.ensure_parsed()
    payload = recipe.to_dict()
    if args.nutrition:
        from based_cooking.nutrition import nutrition_for_recipe

        payload["nutrition"] = nutrition_for_recipe(recipe.parsed_ingredients)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    store = RecipeStore(args.data_dir)
    recipes = store.load_all()
    with_page = sum(1 for r in recipes if r.page is not None)
    with_ing = sum(1 for r in recipes if r.ingredients)
    with_parsed = sum(1 for r in recipes if r.parsed_ingredients)
    sources: dict[str, int] = {}
    chapters: dict[str, int] = {}
    allergen_counts: dict[str, int] = {}
    course_counts: dict[str, int] = {}
    for r in recipes:
        sources[r.source or "(unknown)"] = sources.get(r.source or "(unknown)", 0) + 1
        chapters[r.chapter or "(unknown)"] = chapters.get(r.chapter or "(unknown)", 0) + 1
        course_counts[r.course or "(unknown)"] = course_counts.get(r.course or "(unknown)", 0) + 1
        for a in r.allergens:
            allergen_counts[a] = allergen_counts.get(a, 0) + 1
    print(f"recipes: {len(recipes)}")
    print(f"with page numbers: {with_page}")
    print(f"with ingredients: {with_ing}")
    print(f"with normalized ingredients: {with_parsed}")
    print("by course:")
    for course, count in sorted(course_counts.items(), key=lambda x: -x[1]):
        print(f"  {count:4d}  {course}")
    print("by source:")
    for source, count in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"  {count:4d}  {source}")
    print("top chapters:")
    for chapter, count in sorted(chapters.items(), key=lambda x: -x[1])[:12]:
        print(f"  {count:4d}  {chapter}")
    if allergen_counts:
        print("allergen coverage (recipes tagged):")
        for allergen, count in sorted(allergen_counts.items(), key=lambda x: -x[1]):
            print(f"  {count:4d}  {allergen}")
    return 0


def cmd_normalize(args: argparse.Namespace) -> int:
    store = RecipeStore(args.data_dir)
    recipes = store.normalize_all()
    with_parsed = sum(1 for r in recipes if r.parsed_ingredients)
    with_allergens = sum(1 for r in recipes if r.allergens)
    print(f"Normalized {len(recipes)} recipes")
    print(f"With parsed ingredients: {with_parsed}")
    print(f"With allergen tags: {with_allergens}")
    print(f"Wrote {store.jsonl_path}")
    print(f"Wrote {store.db_path}")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    store = RecipeStore(args.data_dir)
    include = _parse_csv(args.include)
    hits = store.search(
        args.query,
        limit=args.limit,
        include=include,
        exclude=_parse_csv(args.exclude),
        diet=args.diet or None,
        course=(args.course or "").strip() or None,
    )
    cards = []
    for recipe in hits:
        recipe.ensure_parsed()
        card = {
            "id": recipe.id,
            "name": recipe.name,
            "source": recipe.source,
            "url": recipe.url,
            "page": recipe.page,
            "chapter": recipe.chapter,
            "course": recipe.course,
            "yield": recipe.yield_text,
            "description": recipe.description,
            "allergens": recipe.allergens,
            "ingredients": recipe.ingredients,
            "ingredients_normalized": [p.display() for p in recipe.parsed_ingredients],
            "steps": [
                {"text": step.text, "ingredients": step.ingredients}
                for step in recipe.steps
            ],
        }
        if args.nutrition:
            from based_cooking.nutrition import nutrition_for_recipe

            card["nutrition"] = nutrition_for_recipe(recipe.parsed_ingredients)
        cards.append(card)
    payload = {
        "query": args.query,
        "include": include,
        "exclude": _parse_csv(args.exclude),
        "diet": args.diet or None,
        "course": (args.course or "").strip() or None,
        "recipe_count": len(cards),
        "recipes": cards,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_scale(args: argparse.Namespace) -> int:
    from based_cooking.servings import parse_servings, scale_recipe

    store = RecipeStore(args.data_dir)
    recipe = store.get(args.recipe_id)
    if recipe is None:
        print(f"Not found: {args.recipe_id}", file=sys.stderr)
        return 1
    scaled = scale_recipe(recipe, args.servings)
    payload = scaled.to_dict()
    payload["original_servings"] = parse_servings(recipe.yield_text)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    from datetime import date

    from based_cooking.plan import MealHistory, plan_week

    store = RecipeStore(args.data_dir)
    start = date.fromisoformat(args.start) if args.start else date.today()
    history = MealHistory(Path(args.data_dir) / "meal_history.jsonl")
    try:
        plan = plan_week(
            store,
            days=args.days,
            servings=args.servings,
            start=start,
            diet=args.diet or None,
            exclude=_parse_csv(args.exclude),
            include=_parse_csv(args.include),
            with_sides=not args.no_sides,
            cooldown_days=args.cooldown,
            history=history,
            query=args.query,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.save:
        history.append(plan)
    if args.json:
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        return 0
    print(
        f"Meal plan {plan.start} · {plan.days} days · {plan.servings:g} servings each"
    )
    scores = plan.scores
    print(
        "  overlap {overlap:.2f}  flavor-diversity {div:.2f}  "
        "proteins {prot}  adjacent-protein-repeats {adj}  shopping SKUs {sku}".format(
            overlap=scores.get("ingredient_overlap", 0),
            div=scores.get("flavor_diversity", 0),
            prot=int(scores.get("unique_proteins", 0)),
            adj=int(scores.get("adjacent_protein_repeats", 0)),
            sku=int(scores.get("shopping_skus", 0)),
        )
    )
    current_day = None
    for meal in plan.meals:
        if meal.day != current_day:
            current_day = meal.day
            print(f"\n{meal.day} {meal.date}")
        print(f"  {meal.course:4}  {meal.recipe.name}  [{meal.recipe.id}]")
        preview = ", ".join(p.display() for p in meal.recipe.parsed_ingredients[:4])
        more = "…" if len(meal.recipe.parsed_ingredients) > 4 else ""
        print(f"        {preview}{more}")
    print("\nShopping list")
    for row in plan.shopping_list()[:40]:
        print(f"  - {row.get('display') or row.get('item')}")
    leftover = len(plan.shopping_list()) - 40
    if leftover > 0:
        print(f"  … {leftover} more")
    if args.save:
        print(f"\nSaved to {history.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
