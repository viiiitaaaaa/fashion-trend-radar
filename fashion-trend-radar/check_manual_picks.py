"""
Diagnostic: for each manually-picked AliExpress product URL that's missing from
the apify-sourced gallery (data/exports/plaid_skirt_apify_20260915_183350.csv),
visit the live product page via Dolphin (profile 859648353) and read its
current price/rating/sold count, to explain why it didn't make the cut.
"""
import json
import re
import sys
import time

sys.path.insert(0, r"C:\Users\User\dolphin_anty")
from dolphin import DolphinLocal, start_with_retry  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PROFILE = 859648353

with open(r"C:\Users\User\AppData\Local\Temp\missing2.txt", encoding="utf-8") as f:
    missing_ids = [l.strip() for l in f if l.strip()]

results = []

api = DolphinLocal(port=DolphinLocal.discover() or 3001)
data = start_with_retry(api, PROFILE, no_tabs=True)
auto = data["automation"]

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"ws://127.0.0.1:{auto['port']}{auto['wsEndpoint']}")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.new_page()

    for i, pid in enumerate(missing_ids):
        url = f"https://www.aliexpress.us/item/{pid}.html"
        row = {"id": pid, "url": url}
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)

            price_el = page.query_selector('[class*="price-default--wrap"]')
            price_txt = price_el.inner_text() if price_el else ""
            m = re.search(r"\$([\d.]+)", price_txt)
            row["price"] = float(m.group(1)) if m else None

            rating_el = page.query_selector('[class*="reviewer--rating"]')
            row["rating"] = float(rating_el.inner_text().strip()) if rating_el and rating_el.inner_text().strip() else None

            sold_el = page.query_selector('[class*="trade--wrap"], [class*="sold"]')
            sold_txt = sold_el.inner_text() if sold_el else ""
            m2 = re.search(r"([\d,]+)\s*sold", sold_txt, re.I)
            row["orders"] = int(m2.group(1).replace(",", "")) if m2 else None
            row["title"] = page.title()
        except Exception as e:
            row["error"] = str(e)[:200]
        results.append(row)
        print(f"[{i+1}/{len(missing_ids)}]", row.get("price"), row.get("rating"), row.get("orders"), row.get("error", ""))
        time.sleep(1.5)

    page.close()
    browser.close()

with open("data/exports/manual_picks_check.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("done, saved to data/exports/manual_picks_check.json")
