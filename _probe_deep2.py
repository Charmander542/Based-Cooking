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

# ========== SFAH h2rec ==========
print("==== SFAH h2rec ====")
h2rec_files = []
for f in Path("_probe/sfah").rglob("*.html"):
    raw = read(f)
    n = len(re.findall(r'class="h2rec', raw))
    if n:
        h2rec_files.append((n, f))
h2rec_files.sort(reverse=True)
print("h2rec files", [(n, f.name) for n,f in h2rec_files[:15]], "total files", len(h2rec_files), "total h2rec", sum(n for n,_ in h2rec_files))

f = h2rec_files[0][1]
raw = read(f)
s = soup(f)
recs = s.find_all(class_=re.compile(r"^h2rec"))
print("sample titles:", [r.get_text(" ", strip=True)[:80] for r in recs[:8]])
# structure after first h2rec
r0 = recs[0]
nodes = [r0]
for sib in r0.next_siblings:
    if getattr(sib, "get", None):
        cs = " ".join(sib.get("class") or [])
        if cs.startswith("h2rec") or cs == "h2rec" or "h2rec" in cs.split():
            break
    if getattr(sib, "name", None):
        nodes.append(sib)
    if len(nodes) > 40:
        break
sk = []
for n in nodes:
    cs = " ".join(n.get("class") or [])
    txt = n.get_text(" ", strip=True)[:100]
    sk.append(f"<{n.name} class=\"{cs}\">{txt}")
print("SKELETON:\n" + "\n".join(sk[:35]))
idx = raw.find("h2rec")
print("RAW:\n", raw[max(0,idx-100):idx+2000][:2000])

# Also check item/list classes near recipes
print("\nclasses near recipe: item, list, itemb, item1, right2, hr")
for name in ["item","list","itemb","item1","right2","hr","h5","semi","bull1"]:
    print(name, sum(1 for _ in Path("_probe/sfah").rglob("*.html") for __ in [1] if True))  # placeholder

c = Counter()
for f in Path("_probe/sfah").rglob("*.html"):
    raw = read(f)
    for name in ["h2rec","h2rec1","item","list","itemb","item1","right2","hr","h5","semi","orange"]:
        c[name] += len(re.findall(rf'class="{name}"', raw)) + len(re.findall(rf'class="{name} ', raw))
print("counts", dict(c))

# ========== FOODLAB ==========
print("\n==== FOODLAB ====")
cc = Counter()
for f in Path("_probe/foodlab").rglob("*.html"):
    raw = read(f)
    for m in re.findall(r'class="([^"]+)"', raw):
        for x in m.split():
            if re.search(r"rec|ingred|step|yield|serve|method|direct", x, re.I):
                cc[x] += 1
print("recipeish classes", cc.most_common(40))

# count recipe_rt etc
c2 = Counter()
for f in Path("_probe/foodlab").rglob("*.html"):
    raw = read(f)
    for name in ["recipe_rt","recipe_i","recipe_y","recipe_rsteps","recipe_rsteps1","recipe_steph","recipe_hnindnew","srecipe","side-recipe","a-head","b-head","c-head","d-head","shead"]:
        c2[name] += len(re.findall(rf'class="[^"]*{re.escape(name)}[^"]*"', raw))
print("specific", dict(c2))

# find a file with recipe_rt
rt_files = []
for f in Path("_probe/foodlab").rglob("*.html"):
    raw = read(f)
    n = len(re.findall(r'recipe_rt', raw))
    if n:
        rt_files.append((n, f))
rt_files.sort(reverse=True)
print("recipe_rt files", [(n,f.name) for n,f in rt_files[:10]])
if rt_files:
    f = rt_files[0][1]
    raw = read(f)
    s = soup(f)
    rts = s.find_all(class_=re.compile(r"recipe_rt"))
    print("titles", [t.get_text(" ",strip=True)[:80] for t in rts[:5]])
    r0 = rts[0]
    nodes=[r0]
    for sib in r0.next_siblings:
        if getattr(sib,"get",None):
            cs=" ".join(sib.get("class") or [])
            if "recipe_rt" in cs:
                break
        if getattr(sib,"name",None):
            nodes.append(sib)
        if len(nodes)>40: break
    sk=[]
    for n in nodes:
        cs=" ".join(n.get("class") or [])
        txt=n.get_text(" ",strip=True)[:100]
        sk.append(f"<{n.name} class=\"{cs}\">{txt}")
    print("SKELETON:\n"+"\n".join(sk[:35]))
    idx=raw.find("recipe_rt")
    print("RAW:\n", raw[max(0,idx-80):idx+2200][:2200])

# Also try recipe_i as start
i_files=[]
for f in Path("_probe/foodlab").rglob("*.html"):
    raw=read(f)
    n=len(re.findall(r'class="[^"]*recipe_i[^"]*"', raw))
    if n: i_files.append((n,f))
i_files.sort(reverse=True)
print("recipe_i files top", [(n,f.name) for n,f in i_files[:8]], "total", sum(n for n,_ in i_files))
