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

# ========== WOK ==========
print("==== WOK ====")
cc = Counter()
for f in Path("_probe/wok").rglob("*.xhtml"):
    raw = read(f)
    for m in re.findall(r'class="([^"]+)"', raw):
        for x in m.split():
            cc[x] += 1
print("top classes", cc.most_common(50))
recish = [(k,v) for k,v in cc.items() if re.search(r"rec|ingred|step|yield|serve|method|rn|rdt|ing", k, re.I)]
recish.sort(key=lambda x:-x[1])
print("recipeish", recish[:40])

# look for Ingredients text
ing=[]
for f in Path("_probe/wok").rglob("*.xhtml"):
    raw=read(f)
    n=len(re.findall(r"Ingredients", raw))
    if n: ing.append((n,f))
ing.sort(reverse=True)
print("Ingredients files", [(n,f.name) for n,f in ing[:15]], "sum", sum(n for n,_ in ing))

# class rec
print("rec count", cc.get("rec"), "recipe_rn", cc.get("recipe_rn"), "recipe_rns", cc.get("recipe_rns"))
# find file with class=rec heavily
rec_files=[]
for f in Path("_probe/wok").rglob("*.xhtml"):
    raw=read(f)
    n=len(re.findall(r'class="rec"', raw))+len(re.findall(r'class="rec ', raw))
    if n: rec_files.append((n,f))
rec_files.sort(reverse=True)
print("rec files", [(n,f.name) for n,f in rec_files[:12]])

if rec_files:
    f=rec_files[0][1]
    raw=read(f)
    s=soup(f)
    # find elements with class rec
    els=s.find_all(class_="rec")
    print("first rec texts:", [e.name+":"+e.get_text(" ",strip=True)[:60] for e in els[:10]])
    # find recipe_rn
rn_files=[]
for f in Path("_probe/wok").rglob("*.xhtml"):
    raw=read(f)
    if "recipe_rn" in raw or "recipe_rns" in raw or "recipe_rdt" in raw:
        rn_files.append(f)
print("rn files", [f.name for f in rn_files[:20]], "count", len(rn_files))

# Better: search for Serves / NOTES / Directions patterns
for pattern in [r"SERVES", r"Serves", r"NOTES", r"Directions", r"INGREDIENTS", r"Ingredients", r"YIELD", r"Makes "]:
    total=0
    for f in Path("_probe/wok").rglob("*.xhtml"):
        total += len(re.findall(pattern, read(f)))
    print(f"pattern {pattern!r}: {total}")

# Look at Chapter with many rec
if rec_files:
    f = [ff for n,ff in rec_files if "Chapter" in ff.name][0] if any("Chapter" in ff.name for n,ff in rec_files) else rec_files[0][1]
    # pick Chapter002
    f = Path("_probe/wok/OEBPS/xhtml/Chapter002.xhtml")
    raw=read(f)
    print("Chapter002 sample classes around rec")
    idx=raw.find('class="rec"')
    print(raw[max(0,idx-300):idx+1500][:1800])

# Also check Introduction which had many rec
f=Path("_probe/wok/OEBPS/xhtml/Introductiona.xhtml")
raw=read(f)
idx=raw.find('class="rec"')
print("\nIntro rec raw:\n", raw[max(0,idx-200):idx+800])

# Find headings that look like recipe titles - class patterns
for cls in ["cn","ct","h1","ch_h","rh","rn","recipe_rn","bm_h","sans"]:
    pass

# Look for pagebreak + title patterns  
pb=0
for f in Path("_probe/wok").rglob("*.xhtml"):
    pb += len(re.findall(r"pagebreak", read(f), re.I))
print("pagebreaks", pb)

# Inspect a chapter file structure more carefully - list unique classes in Chapter003 or similar
for ch in sorted(Path("_probe/wok/OEBPS/xhtml").glob("Chapter*.xhtml"))[:5]:
    raw=read(ch)
    c=Counter()
    for m in re.findall(r'class="([^"]+)"', raw):
        for x in m.split(): c[x]+=1
    print(ch.name, "top", c.most_common(15), "Ingredients", raw.count("Ingredients"), "Serves", len(re.findall(r"Serves|SERVES", raw)))
