# -*- coding: utf-8 -*-
import warnings, re
from pathlib import Path
from collections import Counter
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

def read(p):
    return Path(p).read_text(encoding="utf-8", errors="replace")

def soup(p):
    return BeautifulSoup(read(p), "lxml")

# WOK: chap_hd as title + old_y
print("==== WOK TITLES ====")
f=Path("_probe/wok/OEBPS/xhtml/Chapter020.xhtml")
raw=read(f)
print(raw[:4000])
print("\n==== Chapter068 ====")
print(read("_probe/wok/OEBPS/xhtml/Chapter068.xhtml")[:3500])

# How often is title chap_hd vs recipe_rn
chap_with_ing=0
chap_hd_and_ing=0
for f in Path("_probe/wok/OEBPS/xhtml").glob("Chapter*.xhtml"):
    raw=read(f)
    if "ing-list" in raw:
        chap_with_ing+=1
        if "chap_hd" in raw:
            chap_hd_and_ing+=1
print("chapters with ing-list", chap_with_ing, "also chap_hd", chap_hd_and_ing)

# recipe_rn usage
for f in Path("_probe/wok/OEBPS/xhtml").glob("Chapter*.xhtml"):
    raw=read(f)
    if 'class="recipe_rn"' in raw or "class=\"recipe_rn " in raw:
        print("recipe_rn file", f.name)
        idx=raw.find("recipe_rn")
        print(raw[max(0,idx-100):idx+500][:600])
        break

# old_y
for f in Path("_probe/wok/OEBPS/xhtml").glob("Chapter*.xhtml"):
    raw=read(f)
    if "old_y" in raw and "ing-list" in raw:
        idx=raw.find("old_y")
        print("old_y sample", f.name, raw[max(0,idx-200):idx+400][:600])
        break

# dir / numberg for steps
for f in Path("_probe/wok/OEBPS/xhtml").glob("Chapter*.xhtml"):
    raw=read(f)
    if "numberg" in raw and "ing-list" in raw and "dir" in raw:
        print("numbered steps file", f.name)
        # find dir section
        idx=raw.find('class="dir"')
        print(raw[idx:idx+1200][:1200])
        break

print("\n==== SHEETPAN RH ====")
c=0
titles=[]
for f in Path("_probe/sheetpan").rglob("*.xhtml"):
    s=soup(f)
    for t in s.find_all(class_=re.compile(r"\bRH\b")):
        c+=1
        titles.append(t.get_text(" ",strip=True)[:80])
print("RH count", c, "sample", titles[:8])

print("\n==== KEEP SIMPLE instructions ====")
raw=read("_probe/keep_simple/OEBPS/xhtml/c01.xhtml")
# find ol after ingredients
idx=raw.find("ingredients")
print(raw[idx:idx+1500][:1500])
# what is rp?
idx=raw.find('class="rp"')
print("rp context", raw[max(0,idx-80):idx+300])

print("\n==== MARTHA yield ====")
raw=read("_probe/martha/OEBPS/Livi_9780307954428_epub_c02_r1.htm")
idx=raw.find("recipe_title")
print(raw[max(0,idx-400):idx+2000][:2400])

# existing adapters?
print("\n==== CODEBASE ====")
for p in Path(".").rglob("*"):
    if p.is_file() and any(x in p.name.lower() for x in ["epub","parser","adapter","joy"]):
        if "_probe" in str(p) or "z-library" in str(p).lower() or p.suffix==".epub":
            continue
        print(p)
