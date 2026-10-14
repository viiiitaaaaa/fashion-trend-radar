"""
Temu (US) search for the radar candidates — the open Dolphin profile 3, logged in by the user (23.09.2026; Temu shows
search only after login, treg.to has no Temu). Page 1 of the search, ~20-40 products: title, price, «N sold».
How many similar products exist and how many are already sold — demand and saturation on the cheapest marketplace.
Human pace, stops after 2 blocked pages (no bypassing). Partial runs replace only their own candidates.
Output: data/processed/temu.csv (per candidate), data/processed/temu_products.csv
Usage: .venv/Scripts/python.exe run_temu.py ["candidate" ...]
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

OUT, OUT_P = Path("data/processed/temu.csv"), Path("data/processed/temu_products.csv")
JS = r"""() => {
  const out = [], seen = new Set();
  for (const a of document.querySelectorAll('a[href*="-g-"]')) {
    const m = a.href.match(/-g-(\d+)\.html/); if (!m || seen.has(m[1])) continue;
    let card = a; for (let i = 0; i < 8 && card.parentElement; i++) { card = card.parentElement; if (/sold/i.test(card.innerText) && /\$\d/.test(card.innerText)) break; }
    seen.add(m[1]);
    out.push({id: m[1], link: a.href.split('?')[0], title: (a.getAttribute('title') || '').slice(0, 140), card: card.innerText.replace(/\s+/g, ' ').slice(0, 500)});
  }
  return out;
}"""


def qty(s):
    s = s.upper().replace(",", "").replace("+", "")
    return int(float(s[:-1]) * 1000) if s.endswith("K") else int(float(s[:-1]) * 1e6) if s.endswith("M") else int(float(s))


def parse(raw):
    rows = []
    for r in raw:
        card = r["card"]
        body = card.split("Open in new tab", 1)[-1]          # the first product of the card
        price = re.search(r"\$(\d+(?:\.\d+)?)", body)
        no_prices = re.sub(r"\$\d+(?:\.\d{1,2})?", " ", body)   # prices and «1.2K+sold» are glued together in the text
        sold = re.search(r"(\d+(?:[.,]\d+)?[KM]?)\+?\s*sold", no_prices, re.I)
        title = r["title"] or card.split("Open in new tab", 1)[0][-140:]
        rows.append({"id": r["id"], "link": r["link"], "title": title.strip(), "price": float(price.group(1)) if price else None,
                     "sold": qty(sold.group(1)) if sold else 0, "ad": card.startswith("AD")})
    return rows


def save(rows, path):
    new = pd.DataFrame(rows)
    if path.exists() and not new.empty:
        old = pd.read_csv(path)
        new = pd.concat([old[~old["candidate"].isin(new["candidate"])], new], ignore_index=True)
    new.to_csv(path, index=False, encoding="utf-8-sig")


def main():
    cands = sys.argv[1:] or pd.read_csv("config/candidates.csv")["candidate"].tolist()
    summary, products, blocked = [], [], 0
    with sync_playwright() as p:
        page = p.chromium.connect_over_cdp(cdp_endpoint()).contexts[0].new_page()
        try:
            for c in cands:
                q = c if "women" in c else f"{c} women"
                page.goto("https://www.temu.com/search_result.html?search_key=" + urllib.parse.quote(q), timeout=90000,
                          wait_until="domcontentloaded")
                time.sleep(random.uniform(7, 10))
                if "login" in page.url or re.search(r"captcha|verify you are human", page.inner_text("body")[:3000], re.I):
                    blocked += 1
                    print(f"  {c}: Temu просит вход/проверку ({blocked}/2)")
                    if blocked >= 2:
                        print("  Стоп: дальше не идём (обход запрещён).")
                        break
                    continue
                for _ in range(4):
                    page.mouse.wheel(0, 1600)
                    time.sleep(random.uniform(1.2, 2.0))
                ps = parse(page.evaluate(JS))
                for x in ps:
                    x["candidate"] = c
                products += ps
                prices = [x["price"] for x in ps if x["price"]]
                top = max(ps, key=lambda x: x["sold"]) if ps else None
                summary.append({"candidate": c, "query": q, "products": len(ps), "with_sales": sum(1 for x in ps if x["sold"]),
                                "sold_total": sum(x["sold"] for x in ps), "sold_top": top["sold"] if top else 0,
                                "top_link": top["link"] if top else "", "price_median": round(statistics.median(prices), 2) if prices else None,
                                "date": str(date.today())})
                s = summary[-1]
                print(f"  {c:<24} товаров {s['products']:>3}, продано всего {s['sold_total']:>9,}, лидер {s['sold_top']:>8,}, цена ~${s['price_median']}")
                time.sleep(random.uniform(8, 14))
        finally:
            page.close()
    if summary:
        save(summary, OUT)
        save(products, OUT_P)
        print(f"Сохранено: {OUT}, {OUT_P}")


if __name__ == "__main__":
    main()
