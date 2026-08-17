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

# ========== WOK full recipe ==========
print("==== WOK RECIPE ====")
# Chapter003 has ing-list
f = Path("_probe/wok/OEBPS/xhtml/Chapter003.xhtml")
raw = read(f)
print(raw[:3500])
print("---")
# Find a fuller recipe chapter - look for recipe_rns + ing-list
best=[]
for f in Path("_probe/wok/OEBPS/xhtml").glob("Chapter*.xhtml"):
    raw=read(f)
    if "recipe_rns" in raw and "ing-list" in raw and "dir" in raw:
        best.append((raw.count("ing-list"), f))
best.sort(reverse=True)
print("best recipe chapters", [(n,f.name) for n,f in best[:10]])
f=best[0][1]
raw=read(f)
s=soup(f)
# find recipe_rns
rns=s.find_all(class_=re.compile(r"recipe_rn"))
print("recipe_rn* count", len(rns), "samples", [x.get_text(" ",strip=True)[:70] for x in rns[:5]])
r0=rns[0]
nodes=[r0]
for sib in r0.next_siblings:
    if getattr(sib,"get",None):
        cs=" ".join(sib.get("class") or [])
        if re.search(r"recipe_rn", cs):
            break
    if getattr(sib,"name",None):
        nodes.append(sib)
    if len(nodes)>50: break
sk=[]
for n in nodes:
    cs=" ".join(n.get("class") or [])
    txt=n.get_text(" ",strip=True)[:110]
    sk.append(f"<{n.name} class=\"{cs}\">{txt}")
print("SKELETON:\n"+"\n".join(sk[:40]))
idx=raw.find("recipe_rns")
if idx<0: idx=raw.find("recipe_rn")
print("RAW:\n", raw[max(0,idx-50):idx+2500][:2500])

# counts
c=Counter()
for f in Path("_probe/wok").rglob("*.xhtml"):
    raw=read(f)
    for name in ["recipe_rns","recipe_rn","ing-list","ing-h","ing-ts","ing-hb","dir","chap_hd","old_y","old_ypara","numberg","crlg","numr","tbs","Serves"]:
        if name=="Serves":
            c[name]+=len(re.findall(r"Serves", raw))
        else:
            c[name]+=len(re.findall(rf'class="{name}"', raw))+len(re.findall(rf'class="{name} ', raw))
print("WOK COUNTS", dict(c))

# ========== KEEP SIMPLE full with instructions ==========
print("\n==== KEEP SIMPLE ====")
f=Path("_probe/keep_simple/OEBPS/xhtml/c01.xhtml")
raw=read(f)
s=soup(f)
rt=s.find(class_="rt")
nodes=[rt]
for sib in rt.next_siblings:
    if getattr(sib,"get",None) and "rt" in (sib.get("class") or []):
        break
    if getattr(sib,"name",None):
        nodes.append(sib)
    if len(nodes)>40: break
sk=[]
for n in nodes:
    cs=" ".join(n.get("class") or [])
    txt=n.get_text(" ",strip=True)[:100]
    sk.append(f"<{n.name} class=\"{cs}\">{txt}")
print("\n".join(sk[:35]))
# count h2.rt across book
c=Counter()
for f in Path("_probe/keep_simple").rglob("*.xhtml"):
    raw=read(f)
    for name in ["rt","ril","rp","ry","ry_img","ct","ingredients","project_img"]:
        c[name]+=len(re.findall(rf'class="{name}"', raw))+len(re.findall(rf'class="{name} ', raw))
print("KEEP COUNTS", dict(c))
# How are instructions? class rp
idx=raw.find('class="rp"')
print("rp sample", raw[idx:idx+400])

# ========== NIGELLA ==========
print("\n==== NIGELLA ====")
f=Path("_probe/nigella/OEBPS/chapter008-10.html")
raw=read(f)
# show full first recipe abbreviated
s=soup(f)
rec=s.find(class_="recipe")
# print children summary
for child in list(rec.children)[:]:
    if getattr(child,"name",None):
        cs=" ".join(child.get("class") or [])
        txt=child.get_text(" ",strip=True)[:90]
        print(f"<{child.name} class=\"{cs}\">{txt}")
        if cs in ("ingredients","procedure","step"):
            for sub in child.find_all(True, recursive=False)[:6]:
                scs=" ".join(sub.get("class") or [])
                print(f"  <{sub.name} class=\"{scs}\">{sub.get_text(' ',strip=True)[:80]}")

c=Counter()
for f in Path("_probe/nigella").rglob("*.html"):
    raw=read(f)
    for name in ["recipe","recipe-title","recipe-title2","ingredients","ingredient","procedure","step","step1","headnote","ingredients-title"]:
        c[name]+=len(re.findall(rf'class="{name}"', raw))+len(re.findall(rf'class="{name} ', raw))
print("NIGELLA COUNTS", dict(c))
# unique recipe titles
titles=[]
for f in Path("_probe/nigella").rglob("*.html"):
    s=soup(f)
    for t in s.find_all(class_=re.compile(r"^recipe-title")):
        titles.append(t.get_text(" ",strip=True)[:100])
print("unique recipe-title count", len(titles))
print("div.recipe count", c["recipe"])

# ========== FOODLAB title variants ==========
print("\n==== FOODLAB TITLES ====")
c=Counter()
title_samples=Counter()
for f in Path("_probe/foodlab").rglob("*.html"):
    raw=read(f)
    for name in ["recipe_rt","recipe_rt1","recipe_rt1a","recipe_srt","srecipe_rt","srecipe_srt","recipe_y","recipe_i","recipe_ih","recipe_rsteps","recipe_rsteps1"]:
        c[name]+=len(re.findall(rf'class="{name}"', raw))
# Count distinct recipes: files or title anchors
# Better: count recipe_y as yield per recipe, or recipe_rt* 
# Many recipes split across title lines recipe_rt1a + recipe_rt1
# Count recipe_y as best estimate?
print("class counts", dict(c))
# count elements that start a recipe - look for SERVES in recipe_y
yields=[]
for f in Path("_probe/foodlab").rglob("*.html"):
    s=soup(f)
    for y in s.find_all(class_=re.compile(r"^recipe_y")):
        yields.append(y.get_text(" ",strip=True)[:60])
print("recipe_y count", len(yields), "samples", yields[:8])
# titles
rts=[]
for f in Path("_probe/foodlab").rglob("*.html"):
    s=soup(f)
    for t in s.find_all(class_=re.compile(r"^recipe_rt")):
        rts.append((t.get("class"), t.get_text(" ",strip=True)[:80]))
print("recipe_rt* count", len(rts))
print("class breakdown", Counter(tuple(c) if isinstance(c:=x[0],list) else (c,) for x in rts))
