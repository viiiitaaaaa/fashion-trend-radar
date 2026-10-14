"""
Channel #3: Amazon (US) women's clothing -- Best Sellers + New Releases per
subcategory, one page view each in Dolphin profile 3. Movers & Shakers is
empty for Fashion (checked 8 nodes, 21.09.2026), so we build our own
"movers" by diffing daily Best Sellers snapshots (rank today vs. rank on the
previous snapshot).
Output:
  data/normalized/amazon/amazon_{date}.parquet   (daily snapshot)
  data/processed/amazon_latest.csv               (today + rank change)
"""
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, r"C:\Users\User\dolphin_anty")
from dolphin import DolphinLocal, start_with_retry  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PROFILE = 859648353
NODES = {
    "womens_clothing": "1040660",
    "dresses": "1045024",
    "tops": "2368343011",
    "sweaters": "1044456",
    "skirts": "1045022",
    "jeans": "1048188",
    "pants": "1048184",
    "coats": "1044646",
}
LISTS = {
    "bestsellers": "https://www.amazon.com/gp/bestsellers/fashion/{node}",
    "new_releases": "https://www.amazon.com/gp/new-releases/fashion/{node}",
}
SNAP_DIR = Path("data/normalized/amazon")
SNAP_DIR.mkdir(parents=True, exist_ok=True)


def num(txt):
    m = re.search(r"[\d,.]+", txt or "")
    return float(m.group().replace(",", "")) if m else None


def parse(html, list_name, category):
    s = BeautifulSoup(html, "html.parser")
    rows = []
    for it in s.select("#gridItemRoot"):
        badge = it.select_one(".zg-bdg-text")
        link = it.select_one('a.a-link-normal[href*="/dp/"]')
        asin = re.search(r"/dp/([A-Z0-9]{10})", link["href"]).group(1) if link else None
        title_el = it.select_one("div[class*='line-clamp']") or it.select_one("img")
        title = title_el.get_text(strip=True) if title_el and title_el.name != "img" else (title_el.get("alt") if title_el else None)
        rating_el = it.select_one("i[class*='a-icon-star'] span, span.a-icon-alt")
        reviews_el = it.select_one("a[href*='customerReviews'] span, span.a-size-small")
        price_el = it.select_one("span[class*='p13n-sc-price'], span._cDEzb_p13n-sc-price_3mJ9Z, span.a-color-price")
        img = it.select_one("img")
        rows.append({
            "snapshot_date": str(date.today()),
            "list": list_name,
            "category": category,
            "rank": int(num(badge.get_text()) or 0) if badge else None,
            "asin": asin,
            "title": title,
            "price": num(price_el.get_text()) if price_el else None,
            "rating": num(rating_el.get_text()) if rating_el else None,
            "reviews": num(reviews_el.get_text()) if reviews_el else None,
            "image": img.get("src") if img else None,
            "url": f"https://www.amazon.com/dp/{asin}" if asin else None,
        })
    return rows


def main():
    api = DolphinLocal(port=DolphinLocal.discover() or 3001)
    auto = start_with_retry(api, PROFILE, no_tabs=True)["automation"]
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"ws://127.0.0.1:{auto['port']}{auto['wsEndpoint']}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        for list_name, tpl in LISTS.items():
            for category, node in NODES.items():
                page.goto(tpl.format(node=node), timeout=90000, wait_until="domcontentloaded")
                time.sleep(4)
                for _ in range(6):
                    page.mouse.wheel(0, 1400)
                    time.sleep(1.0)
                got = parse(page.content(), list_name, category)
                print(f"{list_name:13} {category:16} {len(got)} items")
                rows += got
                time.sleep(3)
        page.close()

    df = pd.DataFrame(rows)
    if df.empty:
        print("Ничего не собрано.")
        return
    snap = SNAP_DIR / f"amazon_{date.today()}.parquet"
    df.to_parquet(snap, index=False)

    # own "movers": compare with the previous snapshot, if any
    prev_files = sorted(f for f in SNAP_DIR.glob("amazon_*.parquet") if f != snap)
    df["prev_rank"] = None
    df["rank_change"] = None
    if prev_files:
        prev = pd.read_parquet(prev_files[-1])[["list", "category", "asin", "rank"]].rename(columns={"rank": "prev_rank"})
        df = df.drop(columns=["prev_rank"]).merge(prev, on=["list", "category", "asin"], how="left")
        df["rank_change"] = df["prev_rank"] - df["rank"]  # positive = climbed

    out = Path("data/processed/amazon_latest.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\nВсего строк: {len(df)}; снимок: {snap}; сравнение с прошлым снимком: {'да' if prev_files else 'нет (первый снимок)'}")
    print(f"Сохранено: {out}")


if __name__ == "__main__":
    main()
