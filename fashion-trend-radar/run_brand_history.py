"""
2-year history of brand new-arrivals pages from the Internet Archive (Wayback Machine, free, no key):
one archived copy per month of each brand's "new in" page, product names from its links, and how many of the
new arrivals match each radar item. Shows whether brands have been adding MORE of an item this autumn than last.
Zara names are abbreviated (LTHR MD SKRT), so Zara gets its own abbreviation patterns.
Output: data/processed/brand_history.csv — brand, month, items, one column per candidate (matching items)
Usage: .venv/Scripts/python.exe run_brand_history.py
"""
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from run_retailers import SITES

BRANDS = ["zara", "asos", "abercrombie", "hm", "aritzia", "freepeople", "mango", "urbanoutfitters"]
SINCE = "202409"
OUT = Path("data/processed/brand_history.csv")
CDX = "https://web.archive.org/cdx/search/cdx"
# item -> regex over product names (lower case); Zara abbreviations after the |
ITEMS = {
    "roll neck sweater": r"roll[- ]?neck|turtle ?neck|mock[- ]neck|funnel[- ]neck|\bhgh nck|trtl",
    "bandana cardigan": r"bandana|paisley card",
    "plaid skirt": r"(plaid|tartan|check(ed)?|gingham).*(skirt|skrt)|(skirt|skrt).*(plaid|tartan|check)",
    "faux fur coat": r"faux fur|faux-fur|fx fr|shearling|teddy (coat|jacket)|fur (coat|jacket)",
    "flannel shirt women": r"flannel|flnnl",
    "trench coat": r"trench|trnch",
    "pea coat": r"pea ?coat|peacoat|double[- ]breasted (wool )?coat",
    "leather leggings": r"(leather|faux leather|pu|lthr).*(legging|lggng)",
    "scarf": r"scarf|scrf",
    # radar candidates added 23.09 (names must match config/candidates.csv)
    "triangle scarf": r"triangle.*(scarf|scrf)|(scarf|scrf).*triangle",
    "bandana scarf": r"bandana",
    "cashmere beanie": r"cashmere.*(beanie|hat)|(beanie|hat).*cashmere",
    "knit poncho": r"poncho|pnch|cape",
    "quilt coat": r"quilt(ed)?.*(coat|jacket|jckt)|qltd",
    "utility jacket women": r"utility.*(jacket|jckt)|cargo (jacket|jckt)",
    "knit hat": r"(knit|kn).*(hat|beanie)|beanie",
    "ribbed beanie": r"rib(bed)?.*beanie",
    "leather trench coat": r"(leather|lthr|faux leather).*trench|trench.*(leather|lthr)",
    "blazer with patches": r"(blazer|blzr).*patch|patch.*(blazer|blzr)",
    "leather leggings": r"(leather|faux leather|pu|lthr).*(legging|lggng)",
}


def month_snapshots(url):
    u = re.sub(r"^https?://", "", url)
    r = requests.get(CDX, params={"url": u, "from": SINCE, "output": "json", "filter": "statuscode:200",
                                  "collapse": "timestamp:6", "fl": "timestamp,original"}, timeout=120)
    return r.json()[1:] if r.text.strip() else []


def product_names(html, pat):
    s = BeautifulSoup(html, "html.parser")
    names = {a.get_text(" ", strip=True)[:120].lower() for a in s.select("a[href]")
             if re.search(pat, a["href"]) and len(a.get_text(strip=True)) > 3}
    return names


def main():
    rows = []
    for brand in BRANDS:
        url, pat = SITES[brand]
        try:
            snaps = month_snapshots(url)
        except Exception as e:
            print(f"{brand}: архив не ответил ({e})")
            continue
        print(f"{brand}: {len(snaps)} месяцев")
        for ts, orig in snaps:
            try:
                html = requests.get(f"https://web.archive.org/web/{ts}id_/{orig}", timeout=180).text
            except Exception:
                continue
            names = product_names(html, pat)
            if len(names) < 5:     # page rendered by scripts / error copy — not usable
                continue
            row = {"brand": brand, "month": f"{ts[:4]}-{ts[4:6]}", "items": len(names)}
            for item, rx in ITEMS.items():
                row[item] = sum(bool(re.search(rx, n)) for n in names)
            rows.append(row)
            time.sleep(1.5)
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"Сохранено {len(df)} месяцев-брендов -> {OUT}")
    if not df.empty:
        print(df.groupby("month")[["items"] + list(ITEMS)].sum().tail(14).to_string())


if __name__ == "__main__":
    main()
