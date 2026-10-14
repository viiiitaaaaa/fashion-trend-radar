"""
TikTok Creative Center «Top Products» (US, last 30 days) through the user's logged-in Dolphin profile 3.
Attaches to the ALREADY RUNNING profile via its DevToolsActivePort (no restart -> the user's tabs stay),
opens one new tab, records the JSON the page itself loads, closes only that tab. Human pace. Runs by hand.
Output: data/raw/tiktok_top_products/*.json, data/processed/tiktok_top_products.csv
"""
import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

DATA_DIR = Path(r"C:\Users\User\AppData\Roaming\dolphin_anty\browser_profiles\859648353\data_dir")
URL = "https://ads.tiktok.com/business/creativecenter/top-products/pc/en?period=30&region=US"
RAW = Path("data/raw/tiktok_top_products")
RAW.mkdir(parents=True, exist_ok=True)


def main():
    port, ws = (DATA_DIR / "DevToolsActivePort").read_text().split()[:2]
    caught = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"ws://127.0.0.1:{port}{ws}")
        ctx = browser.contexts[0]
        page = ctx.new_page()

        def on_resp(resp):
            u = resp.url
            if ("top_products" in u or "top_product" in u or "product" in u and "creative_radar" in u) and resp.status == 200:
                try:
                    caught.append({"url": u, "json": resp.json()})
                except Exception:
                    pass

        page.on("response", on_resp)
        page.goto(URL, timeout=90000, wait_until="domcontentloaded")
        time.sleep(12)
        for _ in range(4):
            page.mouse.wheel(0, 1200)
            time.sleep(2)
        final_url, title = page.url, page.title()
        text = page.inner_text("body")[:3000]
        page.close()   # only our tab
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    (RAW / f"{stamp}_capture.json").write_text(json.dumps({"final_url": final_url, "title": title, "text": text,
                                                           "responses": caught}, ensure_ascii=False), encoding="utf-8")
    print("final url:", final_url)
    print("title:", title)
    print("поймано ответов с товарами:", len(caught), [c["url"][:110] for c in caught][:5])
    rows = []
    for c in caught:
        data = c["json"].get("data") if isinstance(c["json"], dict) else None
        for it in (data or {}).get("list", []) if isinstance(data, dict) else []:
            rows.append({k: it.get(k) for k in ("url_title", "first_ecom_category", "second_ecom_category", "ecom_category_name",
                                                "ctr", "cvr", "cpa", "impression", "cost", "like", "share", "comment",
                                                "play_six_rate") if k in it} | {"raw_keys": ",".join(list(it)[:12])})
    if rows:
        pd.DataFrame(rows).to_csv("data/processed/tiktok_top_products.csv", index=False, encoding="utf-8-sig")
        print("товаров:", len(rows))
    else:
        print("Товаров не поймано. Текст страницы:\n", text[:1200])


if __name__ == "__main__":
    main()
