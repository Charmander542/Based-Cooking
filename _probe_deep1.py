# -*- coding: utf-8 -*-
import warnings, re, json
from pathlib import Path
from collections import Counter
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

def read(p):
    return Path(p).read_text(encoding="utf-8", errors="replace")

def soup(p):
    return BeautifulSoup(read(p), "lxml")

def class_counts(root, globs=("*.html","*.xhtml","*.htm")):
    c = Counter()
    files = []
    for g in globs:
        files.extend(Path(root).rglob(g))
    for f in files:
        raw = read(f)
        for m in re.findall(r'class="([^"]+)"', raw):
            for x in m.split():
                c[x] += 1
    return c

out = {}

# ========== MARTHA ==========
print("==== MARTHA ====")
p = Path("_probe/martha/OEBPS/Livi_9780307954428_epub_c02_r1.htm")
s = soup(p)
titles = s.find_all(class_=re.compile(r"^recipe_title"))
print("recipe_title in c02:", len(titles))
rt = titles[0]
# Collect a recipe block: from recipe_image or recipe_title until next recipe_title
blocks = []
all_rt = s.find_all(class_=re.compile(r"recipe_title"))
# Use regex on raw for cleaner skeleton
raw = read(p)
# find first occurrence of recipe_title with surrounding
m = re.search(r'(<div class="recipe_image".*?</div>\s*)?<p class="recipe_title".*?</p>', raw, re.S)
# better manual walk
html_parts = []
start = rt
# include preceding recipe_image / caption if close
prev_img = rt.find_previous(class_="recipe_image")
nodes = []
if prev_img:
    nodes.append(prev_img)
    cap = prev_img.find_next(class_="recipe_caption")
    if cap:
        nodes.append(cap)
nodes.append(rt)
for sib in rt.next_siblings:
    if getattr(sib, "get", None):
        cs = " ".join(sib.get("class") or [])
        if "recipe_title" in cs:
            break
        if sib.name:
            nodes.append(sib)
    if len(nodes) > 40:
        break
skeleton = []
for n in nodes:
    if not getattr(n, "name", None):
        continue
    cs = " ".join(n.get("class") or [])
    txt = n.get_text(" ", strip=True)[:100]
    children_summary = ""
    if "ingredients" in cs:
        items = n.find_all(class_=re.compile(r"IL_item"))
        children_summary = f" [{len(items)} IL_item]"
    if "method" in cs and "method_step" not in cs:
        # method may contain text or steps
        children_summary = f" text_len={len(n.get_text())}"
    skeleton.append(f"<{n.name} class=\"{cs}\">{txt[:80]}{children_summary}")
print("\n".join(skeleton[:30]))

c = Counter()
for f in Path("_probe/martha").rglob("*.htm*"):
    raw = read(f)
    for name in ["recipe_title","recipe_title2","ingredients","method","yield","cook_time","headnote","IL_item","method_step","recipe_image","ingred_value"]:
        c[name] += len(re.findall(rf'class="[^"]*\b{name}\b[^"]*"', raw))
print("martha counts", dict(c))
out["martha_skeleton"] = skeleton[:25]
out["martha_counts"] = dict(c)

# ========== SHEETPAN ==========
print("\n==== SHEETPAN ====")
p = Path("_probe/sheetpan/OEBPS/ch09.xhtml")
raw = read(p)
s = soup(p)
rhs = s.find_all(class_="RH")
print("RH count ch09:", len(rhs), "text0:", rhs[0].get_text(" ", strip=True) if rhs else None)
rh = rhs[0]
nodes = [rh]
for sib in rh.next_siblings:
    if getattr(sib, "get", None) and "RH" in (sib.get("class") or []):
        break
    if getattr(sib, "name", None):
        nodes.append(sib)
    if len(nodes) > 35:
        break
sk = []
for n in nodes:
    cs = " ".join(n.get("class") or [])
    txt = n.get_text(" ", strip=True)[:90]
    sk.append(f"<{n.name} class=\"{cs}\">{txt}")
print("\n".join(sk[:30]))
c = Counter()
for f in Path("_probe/sheetpan").rglob("*.xhtml"):
    raw = read(f)
    for name in ["RH","RI","RP","RY","RPH","CT","AHD","cherry","br1","noindent"]:
        c[name] += len(re.findall(rf'class="{name}"', raw))
print("sheetpan counts", dict(c))
# raw snippet
idx = raw.find('class="RH"')
out["sheetpan_raw"] = raw[max(0,idx-100):idx+1800]
out["sheetpan_skeleton"] = sk[:30]
out["sheetpan_counts"] = dict(c)
print("RAW:\n", out["sheetpan_raw"][:1500])

# ========== SFAH ==========
print("\n==== SFAH ====")
cc = class_counts("_probe/sfah")
print("top classes", cc.most_common(50))
ing_files = []
for f in Path("_probe/sfah").rglob("*.html"):
    raw = read(f)
    n = len(re.findall(r">\s*Ingredients\s*<", raw, re.I))
    n2 = len(re.findall(r"Ingredients", raw))
    if n2:
        ing_files.append((n2, n, str(f)))
ing_files.sort(reverse=True)
print("Ingredient mentions top:", ing_files[:15])
# Also look for SERVES / Makes
serves = []
for f in Path("_probe/sfah").rglob("*.html"):
    raw = read(f)
    n = len(re.findall(r"(SERVES|Makes|YIELD)", raw, re.I))
    if n:
        serves.append((n, f.name))
serves.sort(reverse=True)
print("SERVES/Makes files", serves[:10])

# Find recipe section by looking at h2 with following list
# Check part02 (recipes often in back)
files = sorted(Path("_probe/sfah/ops/xhtml").glob("*.html"))
print("xhtml files sample", [f.name for f in files[:20]], "... total", len(files))
part2 = [f for f in files if "part02" in f.name or "recipe" in f.name.lower()]
print("part02-ish", [f.name for f in part2[:40]], "count", len(part2))

Path("_probe/_deep_partial.json").write_text(json.dumps({
    "martha_counts": out["martha_counts"],
    "martha_skeleton": out["martha_skeleton"],
    "sheetpan_counts": out["sheetpan_counts"],
    "sheetpan_skeleton": out["sheetpan_skeleton"],
    "sheetpan_raw": out["sheetpan_raw"][:2500],
    "sfah_top_classes": cc.most_common(60),
    "sfah_ing_files": ing_files[:20],
    "sfah_serves": [(a,b) for a,b in serves[:15]],
    "sfah_part2": [f.name for f in part2[:50]],
}, indent=2), encoding="utf-8")
print("wrote partial")
