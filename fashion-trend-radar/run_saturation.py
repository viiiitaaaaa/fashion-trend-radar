"""
Market saturation on Amazon US for each radar candidate — page 1 of the search in the open Dolphin profile 3.
How crowded the niche already is:
  - results: "over 50,000 results" line (how many listings exist at all)
  - brands on page 1 (many different brands = no leader, easier to enter)
  - median reviews and share of listings with 1000+ reviews (entrenched sellers = hard to enter)
  - share of sponsored listings (sellers paying for ads = expensive traffic)
  - median price
Stops after 2 captchas (bypassing protection is forbidden).
Output: data/processed/amazon_saturation.csv
Usage: .venv/Scripts/python.exe run_saturation.py
"""
import random
import sys
import re
import statistics
import time
import urllib.parse
from datetime import date
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from run_extra_signals import parse_bought
from run_retailers import cdp_endpoint

OUT = Path("data/processed/amazon_saturation.csv")
MAX_CAPTCHAS = 2


def num(s):
    s = (s or "").replace(",", "").strip().upper()
    m = re.search(r"([\d.]+)\s*([KM]?)", s)
    if not m:
        return None
    return float(m.group(1)) * {"K": 1e3, "M": 1e6}.get(m.group(2), 1)


def parse(html):
    s = BeautifulSoup(html, "html.parser")
    info = s.select_one('[data-component-type="s-result-info-bar"], .s-desktop-toolbar')
    m = re.search(r"of (over )?([\d,]+) results", info.get_text(" ", strip=True) if info else "")
    results = int(m.group(2).replace(",", "")) if m else None
    items = []
    for it in s.select('div[data-component-type="s-search-result"]'):
        txt = it.get_text(" ", strip=True)
        rev = it.select_one('[aria-label$="ratings"], [aria-label*="rating"] + span, a[href*="#customerReviews"] span')
        reviews = num(rev.get_text()) if rev else None
        brand = it.select_one("h2 + div span, .a-row.a-size-base-plus .a-size-base-plus, span.a-size-base-plus")
        price = it.select_one(".a-price .a-offscreen")
        sponsored = bool(it.select_one(".puis-sponsored-label-text, .s-sponsored-label-text, [aria-label*='Sponsored']")) \
            or "Sponsored" in txt or "AdHolder" in " ".join(it.get("class", []))
        items.append({"reviews": reviews or 0, "sponsored": sponsored,
                      "brand": brand.get_text(strip=True) if brand else "",
                      "price": num(price.get_text().replace("$", "")) if price else None})
    return results, items


def main():
    cands = sys.argv[1:] or pd.read_csv("config/candidates.csv")["candidate"].tolist()
    out, bought, captchas = [], [], 0
    with sync_playwright() as p:
        page = p.chromium.connect_over_cdp(cdp_endpoint()).contexts[0].new_page()
        try:
            for cand in cands:
                q = cand if "women" in cand else f"{cand} women"
                page.goto(f"https://www.amazon.com/s?k={urllib.parse.quote_plus(q)}&i=fashion", timeout=90000,
                          wait_until="domcontentloaded")
                time.sleep(random.uniform(3, 5))
                if "validateCaptcha" in page.content() or "/errors/" in page.url:
                    captchas += 1
                    print(f"  {cand}: Amazon показал проверку ({captchas}/{MAX_CAPTCHAS}) — пропускаю")
                    if captchas >= MAX_CAPTCHAS:
                        print("  Стоп: вторая проверка, дальше не идём.")
                        break
                    time.sleep(random.uniform(20, 30))
                    continue
                for _ in range(4):
                    page.mouse.wheel(0, 1500)
                    time.sleep(random.uniform(0.8, 1.5))
                html = page.content()
                results, items = parse(html)
                rb = parse_bought(html)   # same page: «N+ bought in past month» badges (was run_extra_signals.py --amazon)
                wb = [n for _, n in rb if n]
                top = sorted(((n, t) for t, n in rb if n), reverse=True)[:3]
                bought.append({"candidate": cand, "query": q, "items": len(rb), "items_with_bought": len(wb),
                               "bought_sum": int(sum(wb)), "bought_max": int(max(wb)) if wb else 0,
                               "top": " | ".join(f"{int(n)}+ {t}" for n, t in top), "date": str(date.today())})
                organic = [i for i in items if not i["sponsored"]]
                revs = [i["reviews"] for i in organic]
                prices = [i["price"] for i in items if i["price"]]
                brands = {i["brand"].lower() for i in items if i["brand"]}
                row = {"candidate": cand, "query": q, "results": results, "items": len(items),
                       "brands_page1": len(brands),
                       "median_reviews": int(statistics.median(revs)) if revs else None,
                       "share_1000_reviews": round(sum(r >= 1000 for r in revs) / len(revs), 2) if revs else None,
                       "share_sponsored": round(sum(i["sponsored"] for i in items) / len(items), 2) if items else None,
                       "median_price": round(statistics.median(prices), 2) if prices else None,
                       "date": str(date.today())}
                out.append(row)
                print(f"  {cand:<22} результатов {results}, брендов {row['brands_page1']}, медиана отзывов "
                      f"{row['median_reviews']}, с 1000+ отзывов {row['share_1000_reviews']}, реклама {row['share_sponsored']}")
                time.sleep(random.uniform(8, 15))
        finally:
            page.close()
    for rows, path in ((out, OUT), (bought, Path("data/processed/amazon_bought.csv"))):
        if rows:   # partial runs replace only their own candidates
            new = pd.DataFrame(rows)
            if path.exists():
                old = pd.read_csv(path)
                new = pd.concat([old[~old["candidate"].isin(new["candidate"])], new], ignore_index=True)
            new.to_csv(path, index=False, encoding="utf-8-sig")
            print(f"Сохранено: {path}")


if __name__ == "__main__":
    main()
