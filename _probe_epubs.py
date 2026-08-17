# -*- coding: utf-8 -*-
"""Probe cookbook EPUBs for recipe markup patterns."""
import zipfile, shutil, os, re, json, traceback
from pathlib import Path
from collections import Counter, defaultdict
from bs4 import BeautifulSoup, NavigableString

ROOT = Path(r"c:\Users\Charlie Van Hook\Documents\Code\Based-Cooking")
PROBE = ROOT / "_probe"
PROBE.mkdir(exist_ok=True)

BOOKS = [
    ("keep_simple", "keep it simple"),
    ("martha", "martha"),
    ("nigella", "nigella"),
    ("sfah", "salt, fat"),
    ("sheetpan", "sheet pan"),
    ("foodlab", "food lab"),
    ("wok", "the wok"),
]

epubs = list(ROOT.glob("*.epub"))

def find_epub(hint):
    for e in epubs:
        if hint in e.name.lower():
            return e
    return None

CONTENT_EXTS = {".xhtml", ".html", ".htm", ".xml"}

def extract_book(short, epub_path):
    dest = PROBE / short
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    tmp_zip = PROBE / f"{short}_tmp.zip"
    shutil.copy2(epub_path, tmp_zip)
    with zipfile.ZipFile(tmp_zip, "r") as zf:
        zf.extractall(dest)
    tmp_zip.unlink(missing_ok=True)
    return dest

def find_opf(root):
    # container.xml
    container = root / "META-INF" / "container.xml"
    if container.exists():
        soup = BeautifulSoup(container.read_text(encoding="utf-8", errors="replace"), "lxml-xml")
        rootfile = soup.find("rootfile")
        if rootfile and rootfile.get("full-path"):
            return root / rootfile["full-path"]
    # fallback
    for p in root.rglob("*.opf"):
        return p
    return None

def parse_opf(opf_path):
    text = opf_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(text, "lxml-xml")
    title = None
    creators = []
    for t in soup.find_all(["dc:title", "title"]):
        if t.name.endswith("title") or t.name == "title":
            title = t.get_text(strip=True)
            break
    # try with namespace
    for t in soup.find_all(True):
        if t.name and t.name.endswith("title") and not title:
            title = t.get_text(strip=True)
        if t.name and t.name.endswith("creator"):
            creators.append(t.get_text(strip=True))
    # manifest spine
    items = []
    for item in soup.find_all(["item", "opf:item"]):
        href = item.get("href")
        media = item.get("media-type") or item.get("media-type")
        if href:
            items.append({"href": href, "media": media, "id": item.get("id")})
    return {"title": title, "creators": creators, "items": items, "opf_dir": opf_path.parent}

def list_content_files(root):
    files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in CONTENT_EXTS:
            # skip META-INF etc
            if "META-INF" in str(p):
                continue
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            files.append((size, p))
    files.sort(reverse=True)
    return files

RECIPE_CLASS_HINTS = re.compile(
    r"recipe|ingredient|instruction|direction|method|yield|serving|prep.?time|cook.?time|headnote|chapter",
    re.I,
)
HEADING_RECIPE_HINTS = re.compile(
    r"\b(ingredients?|method|directions?|instructions?|preparation|serves?|yield|makes)\b",
    re.I,
)
PAGEBREAK_HINTS = re.compile(r"pagebreak|page-break|epub:type.*pagebreak|pagebreak", re.I)

def class_str(tag):
    c = tag.get("class")
    if not c:
        return ""
    if isinstance(c, list):
        return " ".join(c)
    return str(c)

def analyze_html(path):
    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml")
    classes = Counter()
    tags = Counter()
    id_patterns = Counter()
    for tag in soup.find_all(True):
        tags[tag.name] += 1
        cs = class_str(tag)
        if cs:
            for c in cs.split():
                classes[c] += 1
        tid = tag.get("id")
        if tid:
            # normalize numeric suffixes
            norm = re.sub(r"\d+", "N", tid)
            id_patterns[norm] += 1
    return soup, raw, classes, tags, id_patterns

def collect_signals(files, max_files=25):
    all_classes = Counter()
    all_tags = Counter()
    all_ids = Counter()
    recipeish_classes = Counter()
    samples = []
    for size, path in files[:max_files]:
        try:
            soup, raw, classes, tags, ids = analyze_html(path)
        except Exception as e:
            continue
        all_classes.update(classes)
        all_tags.update(tags)
        all_ids.update(ids)
        for c, n in classes.items():
            if RECIPE_CLASS_HINTS.search(c):
                recipeish_classes[c] += n
        samples.append((size, path, soup, raw))
    return all_classes, all_tags, all_ids, recipeish_classes, samples

def count_headings(soup, levels=("h1", "h2", "h3", "h4")):
    counts = {}
    texts = []
    for lv in levels:
        hs = soup.find_all(lv)
        counts[lv] = len(hs)
        for h in hs:
            t = h.get_text(" ", strip=True)
            if t:
                texts.append((lv, class_str(h), t[:120]))
    return counts, texts

def heuristic_counts(all_files):
    """Various heuristics across all content files."""
    results = {
        "h1": 0, "h2": 0, "h3": 0, "h4": 0,
        "class_recipe": 0,
        "class_contains_recipe": 0,
        "epub_type_recipe": 0,
        "heading_before_ingredients": 0,
        "sections_with_ingredients_and_method": 0,
        "pagebreak_count": 0,
        "strong_recipe_blocks": 0,
    }
    recipe_title_candidates = []
    class_recipe_tags = Counter()
    ingredient_markers = Counter()
    instruction_markers = Counter()
    yield_markers = Counter()

    for size, path in all_files:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # pagebreaks in raw
        results["pagebreak_count"] += len(re.findall(r"pagebreak|page-break|epub:type=[\"']pagebreak", raw, re.I))
        try:
            soup = BeautifulSoup(raw, "lxml")
        except Exception:
            continue

        for lv in ("h1", "h2", "h3", "h4"):
            results[lv] += len(soup.find_all(lv))

        for tag in soup.find_all(True):
            cs = class_str(tag)
            et = tag.get("epub:type") or tag.get("role") or ""
            if cs:
                low = cs.lower()
                if re.search(r"\brecipe\b", low) or "recipe" in low.split():
                    results["class_recipe"] += 1
                    class_recipe_tags[f"{tag.name}.{cs}"] += 1
                if "recipe" in low:
                    results["class_contains_recipe"] += 1
                if re.search(r"ingredient", low):
                    ingredient_markers[f"{tag.name}.{cs}"] += 1
                if re.search(r"instruction|direction|method|step", low):
                    instruction_markers[f"{tag.name}.{cs}"] += 1
                if re.search(r"yield|serving|serves|makes", low):
                    yield_markers[f"{tag.name}.{cs}"] += 1
            if et and "recipe" in str(et).lower():
                results["epub_type_recipe"] += 1

        # heading then ingredients text nearby
        for h in soup.find_all(["h1", "h2", "h3", "h4", "p", "div", "span"]):
            cs = class_str(h)
            text = h.get_text(" ", strip=True)
            if not text or len(text) > 200:
                continue
            # look for title-like + following Ingredients
            if h.name in ("h1", "h2", "h3") or re.search(r"title|recipe.?name|rec-title|chtitle|head", cs, re.I):
                # peek next siblings for Ingredients
                nxt = h.find_next(string=re.compile(r"^\s*Ingredients?\s*$", re.I))
                if nxt:
                    # distance check - within next 15 tags
                    results["heading_before_ingredients"] += 1
                    recipe_title_candidates.append((path.name, text[:100], cs))

        # sections that contain both Ingredients and Method/Directions
        body_text = soup.get_text("\n", strip=True)
        if re.search(r"(?im)^\s*Ingredients?\s*$", body_text) and re.search(
            r"(?im)^\s*(Method|Directions?|Instructions?|Preparation)\s*$", body_text
        ):
            # count occurrences of Ingredients as proxy
            n_ing = len(re.findall(r"(?im)^\s*Ingredients?\s*$", body_text))
            results["sections_with_ingredients_and_method"] += n_ing

    return results, recipe_title_candidates[:30], class_recipe_tags, ingredient_markers, instruction_markers, yield_markers

def find_recipe_snippet(all_files, ingredient_markers, class_recipe_tags):
    """Find a file/region that looks like a full recipe and return abbreviated HTML."""
    snippets = []
    # Prefer files with ingredient class markers
    preferred_classes = [k.split(".", 1)[-1].split()[0] for k, _ in ingredient_markers.most_common(5)]
    recipe_classes = [k.split(".", 1)[-1].split()[0] for k, _ in class_recipe_tags.most_common(5)]

    for size, path in sorted(all_files, reverse=True)[:80]:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            soup = BeautifulSoup(raw, "lxml")
        except Exception:
            continue

        candidates = []
        # by recipe class
        for rc in recipe_classes:
            for tag in soup.find_all(class_=re.compile(re.escape(rc), re.I)):
                candidates.append(tag)
        # by ingredient section
        for tag in soup.find_all(string=re.compile(r"^\s*Ingredients?\s*$", re.I)):
            parent = tag.find_parent(["div", "section", "article", "table", "body"])
            # walk up to find a good container
            node = tag.parent
            for _ in range(8):
                if node is None:
                    break
                # look for preceding heading
                prev_h = node.find_previous(["h1", "h2", "h3", "h4"])
                if prev_h:
                    # collect from prev_h through some following siblings
                    block_parts = [str(prev_h)[:500]]
                    cur = prev_h
                    lines = 0
                    for sib in prev_h.next_siblings:
                        if isinstance(sib, NavigableString):
                            continue
                        block_parts.append(str(sib)[:800])
                        lines += 1
                        if lines >= 12:
                            break
                    candidates.append(("heading_block", prev_h.get_text(strip=True)[:80], "\n".join(block_parts)))
                    break
                node = node.parent

        for tag in soup.find_all(True, class_=True):
            cs = class_str(tag)
            if any(pc.lower() in cs.lower() for pc in preferred_classes if pc):
                # get ancestor with title
                ancestors = list(tag.parents)[:6]
                for anc in [tag] + ancestors:
                    html = str(anc)
                    if 200 < len(html) < 15000:
                        # check has ingredients-ish content
                        txt = anc.get_text(" ", strip=True).lower()
                        if "ingredient" in txt or re.search(r"\d+\s*(cup|tbsp|tsp|ounce|oz|lb|g\b|ml)", txt):
                            title_guess = ""
                            h = anc.find(["h1", "h2", "h3", "h4"]) or anc.find_previous(["h1", "h2", "h3", "h4"])
                            if h:
                                title_guess = h.get_text(strip=True)[:80]
                            candidates.append(("class_block", title_guess, html[:3500]))
                            break

        # also try h2/h3 followed by ingredients
        for h in soup.find_all(["h1", "h2", "h3"]):
            t = h.get_text(strip=True)
            if not t or len(t) < 3 or len(t) > 100:
                continue
            # gather following content
            parts = [str(h)]
            count = 0
            has_ing = False
            for sib in h.next_siblings:
                if isinstance(sib, NavigableString):
                    if sib.strip():
                        parts.append(str(sib))
                    continue
                if sib.name in ("h1", "h2", "h3") and count > 2:
                    break
                st = sib.get_text(" ", strip=True)
                if re.search(r"ingredients?", st, re.I):
                    has_ing = True
                parts.append(str(sib)[:1200])
                count += 1
                if count >= 15:
                    break
            if has_ing and count >= 3:
                snippets.append({
                    "file": path.name,
                    "title": t,
                    "html": "\n".join(parts)[:4000],
                })
                if len(snippets) >= 2:
                    return snippets

        for c in candidates:
            if isinstance(c, tuple) and c[0] in ("heading_block", "class_block"):
                snippets.append({"file": path.name, "title": c[1], "html": c[2][:4000]})
                if len(snippets) >= 2:
                    return snippets

    return snippets[:2]

def abbreviate_html(html, max_lines=40):
    # pretty-ish: split tags onto lines roughly
    html = re.sub(r">\s*<", ">\n<", html)
    lines = html.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... ({len(html.splitlines()) - max_lines} more lines truncated)"]
    # collapse long text nodes
    out = []
    for line in lines:
        if len(line) > 200 and "<" not in line[50:]:
            line = line[:160] + "..."
        out.append(line)
    return "\n".join(out)

def tree_structure(root, max_depth=3):
    """Summarize top-level folder structure."""
    lines = []
    def walk(p, depth):
        if depth > max_depth:
            return
        try:
            kids = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except Exception:
            return
        for k in kids[:40]:
            rel = k.relative_to(root)
            if k.is_dir():
                nfiles = sum(1 for _ in k.rglob("*") if _.is_file())
                lines.append(f"{'  '*depth}{k.name}/ ({nfiles} files)")
                walk(k, depth + 1)
            else:
                if depth <= 2:
                    lines.append(f"{'  '*depth}{k.name}")
    walk(root, 0)
    return "\n".join(lines[:60])

def analyze_book(short, hint):
    epub = find_epub(hint)
    if not epub:
        return {"short": short, "error": "epub not found"}
    print(f"\n=== Extracting {short}: {epub.name[:60]}... ===", flush=True)
    dest = extract_book(short, epub)
    opf = find_opf(dest)
    meta = parse_opf(opf) if opf else {"title": None, "creators": [], "items": [], "opf_dir": dest}
    files = list_content_files(dest)
    print(f"  content files: {len(files)}, opf: {opf}", flush=True)

    all_classes, all_tags, all_ids, recipeish, samples = collect_signals(files, max_files=min(40, len(files)))
    heur, titles, class_recipe_tags, ing_m, inst_m, yield_m = heuristic_counts(files)
    snippets = find_recipe_snippet(files, ing_m, class_recipe_tags)

    # top classes overall and recipeish
    top_classes = all_classes.most_common(40)
    top_recipeish = recipeish.most_common(30)

    # sample largest files heading stats
    largest_info = []
    for size, path, soup, raw in samples[:5]:
        hc, htexts = count_headings(soup)
        largest_info.append({
            "file": str(path.relative_to(dest)),
            "size": size,
            "headings": hc,
            "sample_headings": htexts[:15],
            "top_classes_here": Counter(
                c for t in soup.find_all(True) for c in class_str(t).split() if c
            ).most_common(15),
        })

    # estimate best recipe count
    estimates = {
        "h1": heur["h1"],
        "h2": heur["h2"],
        "h3": heur["h3"],
        "class_recipe_elements": heur["class_recipe"],
        "heading_before_ingredients": heur["heading_before_ingredients"],
        "sections_ing_and_method": heur["sections_with_ingredients_and_method"],
        "epub_type_recipe": heur["epub_type_recipe"],
    }

    report = {
        "short": short,
        "epub_file": epub.name,
        "title": meta["title"],
        "creators": meta["creators"],
        "opf": str(opf.relative_to(dest)) if opf else None,
        "content_file_count": len(files),
        "total_extracted_files": sum(1 for _ in dest.rglob("*") if _.is_file()),
        "structure": tree_structure(dest),
        "top_classes": top_classes,
        "recipeish_classes": top_recipeish,
        "class_recipe_tags": class_recipe_tags.most_common(20),
        "ingredient_markers": ing_m.most_common(20),
        "instruction_markers": inst_m.most_common(20),
        "yield_markers": yield_m.most_common(15),
        "id_patterns": all_ids.most_common(20),
        "heuristics": heur,
        "estimates": estimates,
        "sample_title_candidates": titles[:15],
        "largest_files": largest_info,
        "snippets": [
            {"file": s["file"], "title": s["title"], "html": abbreviate_html(s["html"])}
            for s in snippets
        ],
    }
    out = PROBE / f"{short}_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {out.name}", flush=True)
    return report

def main():
    reports = []
    for short, hint in BOOKS:
        try:
            reports.append(analyze_book(short, hint))
        except Exception as e:
            print(f"ERROR {short}: {e}")
            traceback.print_exc()
            reports.append({"short": short, "error": str(e)})
    (PROBE / "_all_reports.json").write_text(
        json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nDONE", flush=True)

if __name__ == "__main__":
    main()
