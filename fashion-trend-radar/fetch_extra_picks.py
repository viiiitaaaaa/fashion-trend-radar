"""Fetch og:title/og:image for the 15 manually-picked products that pass all
quality filters but were missed by the Apify actor, to add them to the gallery."""
import json
import re
import sys
import time

sys.path.insert(0, r"C:\Users\User\dolphin_anty")
from dolphin import DolphinLocal, start_with_retry  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PROFILE = 859648353

IDS = [
    "3256806128732645", "3256806128946838", "3256806944645028", "3256807922389330",
    "3256808551789699", "3256809242475264", "3256809453986337", "3256809479127611",
    "3256809631289032", "3256809816986243", "3256810076196944", "3256810167031054",
    "3256810249092701", "3256811441544971", "3256811643918083",
]

checked = {r["id"]: r for r in json.load(open("data/exports/manual_picks_check.json", encoding="utf-8"))}

results = []
api = DolphinLocal(port=DolphinLocal.discover() or 3001)
data = start_with_retry(api, PROFILE, no_tabs=True)
auto = data["automation"]

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"ws://127.0.0.1:{auto['port']}{auto['wsEndpoint']}")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.new_page()

    for i, pid in enumerate(IDS):
        url = f"https://www.aliexpress.us/item/{pid}.html"
        row = {"id": pid, "url": url}
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            title_el = page.query_selector('meta[property="og:title"]')
            row["title"] = title_el.get_attribute("content") if title_el else page.title()
            img_el = page.query_selector('meta[property="og:image"]')
            row["image"] = img_el.get_attribute("content") if img_el else None
        except Exception as e:
            row["error"] = str(e)[:200]
        results.append(row)
        print(i + 1, pid, row.get("title", "")[:60], row.get("image", "")[:50])
        time.sleep(1.2)

    page.close()
    browser.close()

merged = []
for r in results:
    c = checked.get(r["id"], {})
    merged.append({
        "keyword": "plaid skirt",
        "title": r.get("title") or "",
        "price": c.get("price"),
        "orders": c.get("orders"),
        "orders_text": f"{c.get('orders')} sold" if c.get("orders") else None,
        "rating": c.get("rating"),
        "url": r["url"],
        "image": r.get("image"),
        "is_choice": False,
        "source": "manual",
    })

with open("data/exports/extra_manual_picks.json", "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)
print("saved", len(merged))
