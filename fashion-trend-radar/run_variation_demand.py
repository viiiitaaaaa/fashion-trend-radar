"""
Demand check for the mid-frequency VARIATIONS of an item (user's «отстройка», 24.09.2026): for every phrase from
data/processed/variations.csv — Amazon US search page 1 (how many listings have «N bought in past month» and the sum)
and Temu US search page 1 (sold). Both in the open Dolphin profile 3, human pace, stop after 2 blocks.
Output: data/processed/variation_demand.csv
Usage: .venv/Scripts/python.exe run_variation_demand.py
"""
import random
import re
import time
import urllib.parse
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

from run_extra_signals import parse_bought
from run_retailers import cdp_endpoint
from run_temu import JS as TEMU_JS, parse as temu_parse

OUT = Path("data/processed/variation_demand.csv")


def main():
    v = pd.read_csv("data/processed/variations.csv")
    done = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame(columns=["variation"])
    rows, blocked = done.to_dict("records"), 0
    with sync_playwright() as p:
        page = p.chromium.connect_over_cdp(cdp_endpoint()).contexts[0].new_page()
        try:
            for r in v.itertuples():
                if r.variation in set(done["variation"]):
                    continue
                q = r.variation if "women" in r.variation else f"{r.variation} women"
                page.goto(f"https://www.amazon.com/s?k={urllib.parse.quote_plus(q)}&i=fashion", timeout=90000, wait_until="domcontentloaded")
                time.sleep(random.uniform(3, 5))
                if "validateCaptcha" in page.content():
                    blocked += 1
                    print("  Amazon: проверка на робота" + (" — стоп" if blocked >= 2 else ""))
                    if blocked >= 2:
                        break
                    time.sleep(25)
                    continue
                for _ in range(4):
                    page.mouse.wheel(0, 1500)
                    time.sleep(random.uniform(0.8, 1.4))
                b = parse_bought(page.content())
                with_b = [n for _, n in b if n]
                page.goto("https://www.temu.com/search_result.html?search_key=" + urllib.parse.quote(q), timeout=90000, wait_until="domcontentloaded")
                time.sleep(random.uniform(7, 9))
                for _ in range(3):
                    page.mouse.wheel(0, 1600)
                    time.sleep(random.uniform(1.2, 1.8))
                t = temu_parse(page.evaluate(TEMU_JS)) if "login" not in page.url else []
                prices = sorted(x["price"] for x in t if x["price"])
                rows.append({"item": r.item, "variation": r.variation, "amazon_items": len(b), "amazon_with_bought": len(with_b),
                             "amazon_bought_sum": int(sum(with_b)), "temu_products": len(t), "temu_sold": sum(x["sold"] for x in t),
                             "temu_price_median": prices[len(prices) // 2] if prices else None})
                x = rows[-1]
                print(f"  {r.variation:<30} Amazon куплено ≥{x['amazon_bought_sum']:>7,} ({x['amazon_with_bought']:>2} тов.) | Temu продано {x['temu_sold']:>8,}")
                pd.DataFrame(rows).to_csv(OUT, index=False, encoding="utf-8-sig")   # saved after every phrase
                time.sleep(random.uniform(5, 9))
        finally:
            page.close()


if __name__ == "__main__":
    main()
