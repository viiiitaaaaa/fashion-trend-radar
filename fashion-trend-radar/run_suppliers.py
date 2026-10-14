"""
Suppliers for the radar's TEST items: AliExpress (.com only — never .ru; opens as aliexpress.us = US prices and
shipping) searched by orders in the open Dolphin profile 3 (859648353 — this store's profile). Keeps only listings
that really are the item (title words), with price, orders, rating, free shipping and delivery dates.
Output: data/processed/suppliers.csv (listings), data/processed/suppliers_summary.csv
Usage: .venv/Scripts/python.exe run_suppliers.py ["candidate" ...]   (default: decision TEST)
"""
import random
import re
import statistics
import sys
import time
import urllib.parse
from datetime import date
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

from run_retailers import cdp_endpoint

OUT, OUT_S = Path("data/processed/suppliers.csv"), Path("data/processed/suppliers_summary.csv")
# candidate -> (search phrases, regex the title must match, regex that excludes wrong items)
QUERIES = {
    "roll neck sweater": (["turtleneck sweater women", "roll neck sweater women"], r"turtleneck|roll ?neck|high neck|mock neck",
                          r"\bmen\b|men's|kids|girl|boy|dog|dress"),
    "knit poncho": (["knit poncho women", "knitted poncho sweater women"], r"poncho|cape", r"\bmen\b|kids|girl|boy|dog|baby|rain|towel|bridal"),
    "plaid skirt": (["plaid skirt women", "plaid mini skirt women"], r"plaid|tartan|check|gingham", r"\bmen\b|kids|girl|boy|dog|school uniform|cosplay"),
    "bandana cardigan": (["bandana print cardigan women", "paisley cardigan women"], r"bandana|paisley", r"\bmen\b|kids|girl|boy|dog"),
    "knit hat": (["knit beanie women"], r"beanie|knit hat", r"\bmen\b|kids|baby|dog"),
}
JS = r"""() => [...new Map([...document.querySelectorAll('a[href*="/item/"]')].map(a => [a.href.split('?')[0],
          a.innerText.replace(/\s+/g, ' ').slice(0, 400)])).entries()]"""


def num(s):
    s = s.replace(",", "").replace("+", "").upper()
    return int(float(s[:-1]) * 1000) if s.endswith("K") else int(float(s))


def parse(pairs, cand):
    _, want, bad = QUERIES[cand]
    out = []
    for link, text in pairs:
        prices = re.findall(r"\$\s?(\d+(?:\.\d{1,2})?)", text)
        if not prices:
            continue
        title = re.split(r"\$\s?\d", text)[0].strip()
        if not re.search(want, title, re.I) or re.search(bad, title, re.I):
            continue
        sold = re.search(r"([\d,.]+K?\+?)\s*sold", text, re.I)
        rating = re.search(r"\s(\d\.\d)\s", text)
        deliv = re.search(r"Delivery:\s*([A-Z][a-z]{2}\.? \d{1,2}\s*-\s*[A-Z]?[a-z]*\.? ?\d{1,2})", text)
        out.append({"candidate": cand, "title": title[:150], "price": float(prices[0]),
                    "orig_price": float(prices[1]) if len(prices) > 1 else None,
                    "sold": num(sold.group(1)) if sold else 0, "rating": float(rating.group(1)) if rating else None,
                    "free_shipping": bool(re.search(r"free shipping|ALL Free", text, re.I)),
                    "delivery": deliv.group(1) if deliv else "", "link": link.replace("aliexpress.us", "aliexpress.com")})
    return out


def main():
    cands = sys.argv[1:] or pd.read_csv("data/reports/radar_candidates.csv").query("decision == 'TEST'")["candidate"].tolist()
    rows = []
    with sync_playwright() as p:
        page = p.chromium.connect_over_cdp(cdp_endpoint()).contexts[0].new_page()
        try:
            for c in cands:
                if c not in QUERIES:
                    print(f"  {c}: нет поисковых фраз в QUERIES — пропускаю")
                    continue
                for q in QUERIES[c][0]:
                    page.goto("https://www.aliexpress.com/w/wholesale-" + urllib.parse.quote(q.replace(" ", "-")) +
                              ".html?SortType=total_tranpro_desc&g=y", timeout=90000, wait_until="domcontentloaded")
                    time.sleep(random.uniform(7, 9))
                    if ".ru" in page.url.split("/")[2]:
                        print("  AliExpress перебросил на .ru — стоп (правило: только .com)")
                        return
                    for _ in range(5):
                        page.mouse.wheel(0, 1800)
                        time.sleep(random.uniform(1.2, 2.0))
                    got = parse(page.evaluate(JS), c)
                    for g in got:
                        g["query"] = q
                    rows += got
                    print(f"  {c:<18} «{q}»: подходящих {len(got)}")
                    time.sleep(random.uniform(5, 8))
        finally:
            page.close()
    df = pd.DataFrame(rows).drop_duplicates("link")
    if df.empty:
        return
    df = df.sort_values(["candidate", "sold"], ascending=[True, False])
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    summ = []
    for c, g in df.groupby("candidate"):
        top = g.head(10)   # the 10 best-selling real matches
        # «new shoppers» deals ($1.09 with an old price of $12–18) are one-off — not a real unit cost
        real = top[(top["price"] >= 4) & ~((top["orig_price"].fillna(0) > 0) & (top["price"] < top["orig_price"] * 0.2))]
        summ.append({"candidate": c, "listings": len(g), "top10_sold": int(top["sold"].sum()),
                     "price_median_top10": round(statistics.median(real["price"]), 2) if len(real) else None,
                     "price_min_top10": real["price"].min() if len(real) else None,
                     "free_shipping_share": round(top["free_shipping"].mean(), 2), "best_link": real.iloc[0]["link"] if len(real) else "",
                     "best_title": real.iloc[0]["title"][:90] if len(real) else "", "best_price": real.iloc[0]["price"] if len(real) else None,
                     "best_sold": int(real.iloc[0]["sold"]) if len(real) else 0,
                     "date": str(date.today())})
    pd.DataFrame(summ).to_csv(OUT_S, index=False, encoding="utf-8-sig")
    print(pd.DataFrame(summ)[["candidate", "listings", "top10_sold", "price_median_top10", "price_min_top10", "best_price", "best_sold"]].to_string(index=False))


if __name__ == "__main__":
    main()
