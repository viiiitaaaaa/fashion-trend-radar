"""
Channel #5: women's new arrivals at Zara, ASOS, Aritzia, Free People (US),
one page view each in Dolphin profile 3. Reads product names/prices from
the product links the page renders, decomposes names with the fashion
taxonomy, and counts which attributes (pattern/material/neckline/
silhouette/detail) show up across SEVERAL brands -- the "supply side"
signal: what brands are betting on right now.
Output:
  data/normalized/retailers/retailers_{date}.parquet
  data/processed/retailer_attributes.csv
"""
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from src.processors.fashion_taxonomy import TAXONOMY, decompose_keywords

sys.path.insert(0, r"C:\Users\User\dolphin_anty")
from dolphin import DolphinLocal, start_with_retry  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PROFILE = 859648353
SITES = {
    "zara": ("https://www.zara.com/us/en/woman-new-in-l1180.html", r"-p\d{6,}\.html"),
    "asos": ("https://www.asos.com/us/women/new-in/new-in-clothing/cat/?cid=2623", r"/prd/\d+"),
    "aritzia": ("https://www.aritzia.com/us/en/new", r"/product/"),
    "freepeople": ("https://www.freepeople.com/new-clothes/", r"/shop/"),
    # added 23.09.2026 (user: «да давай») — more brands, so the supply-side signal covers more items
    "hm": ("https://www2.hm.com/en_us/women/new-arrivals/view-all.html", r"productpage\.\d+"),
    "mango": ("https://shop.mango.com/us/en/c/women/new-now/56b5c5ed", r"/p/women/|_\d{8}"),
    "urbanoutfitters": ("https://www.urbanoutfitters.com/womens-new-arrivals", r"/shop/"),
    "abercrombie": ("https://www.abercrombie.com/shop/us/womens-new-arrivals", r"/shop/us/p/"),
}
DATA_DIR = Path(r"C:\Users\User\AppData\Roaming\dolphin_anty\browser_profiles\859648353\data_dir")
SNAP_DIR = Path("data/normalized/retailers")
SNAP_DIR.mkdir(parents=True, exist_ok=True)


def clean_name(site, raw):
    name = re.split(r",?\s*Price[:\s]", raw)[0]          # ASOS/Aritzia append price
    name = re.sub(r"^(Zara|Top Rated)\s+", "", name, flags=re.I)
    if site == "aritzia":
        name = name.split(" - ")[0] + " " + " ".join(name.split(" - ")[1:2])
    return re.sub(r"\s+", " ", name).strip()


def parse(site, html, pattern, base):
    s = BeautifulSoup(html, "html.parser")
    seen = {}
    for a in s.find_all("a", href=True):
        if not re.search(pattern, a["href"]):
            continue
        raw = (a.get("aria-label") or a.get_text(" ", strip=True) or "").strip()
        img = a.find("img")
        if not raw and img:
            raw = img.get("alt", "")
        href = a["href"].split("?")[0]
        if raw and len(raw) > 3 and href not in seen:
            price = re.search(r"\$\s?([\d,]+(?:\.\d{2})?)", raw)
            seen[href] = {"raw": raw, "price": float(price.group(1).replace(",", "")) if price else None}
    rows = []
    for href, d in seen.items():
        name = clean_name(site, d["raw"])
        # Zara includes a few image captions ("Woman in a ...") -- not products
        if name.lower().startswith(("woman in", "model ")):
            continue
        rows.append({
            "snapshot_date": str(date.today()), "retailer": site, "name": name,
            "price": d["price"], "url": href if href.startswith("http") else base + href,
        })
    return rows


def cdp_endpoint():
    """Attach to the ALREADY OPEN profile (keeps the user's tabs); start it only if it is not running."""
    f = DATA_DIR / "DevToolsActivePort"
    if f.exists():
        port, ws = f.read_text().split()[:2]
        try:
            import requests
            requests.get(f"http://127.0.0.1:{port}/json/version", timeout=5).raise_for_status()
            return f"ws://127.0.0.1:{port}{ws}"
        except Exception:
            pass
    api = DolphinLocal(port=DolphinLocal.discover() or 3001)
    auto = start_with_retry(api, PROFILE, no_tabs=True)["automation"]
    return f"ws://127.0.0.1:{auto['port']}{auto['wsEndpoint']}"


def main():
    only = sys.argv[1:]
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_endpoint())
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        for site, (url, pattern) in SITES.items():
            if only and site not in only:
                continue
            page = ctx.new_page()
            try:
                page.goto(url, timeout=90000, wait_until="domcontentloaded")
                time.sleep(8)
                for _ in range(14):
                    page.mouse.wheel(0, 1300)
                    time.sleep(1.4)
                base = re.match(r"https://[^/]+", url).group()
                got = parse(site, page.content(), pattern, base)
                print(f"{site:11} {len(got)} товаров")
                rows += got
            except Exception as e:
                print(f"{site:11} ОШИБКА: {str(e)[:120]}")
            finally:
                page.close()
            time.sleep(5)

    df = pd.DataFrame(rows)
    if df.empty:
        print("Ничего не собрано.")
        return
    df = decompose_keywords(df, keyword_col="name")
    snap = SNAP_DIR / f"retailers_{date.today()}.parquet"
    df.to_parquet(snap, index=False)

    # attribute -> in how many brands / how many items
    groups = [g for g in TAXONOMY if g != "category"]
    agg = []
    for g in groups:
        ex = df.assign(attr=df[g].fillna("").str.split("|")).explode("attr")
        ex = ex[ex["attr"] != ""]
        for attr, sub in ex.groupby("attr"):
            agg.append({"group": g, "attribute": attr, "brands": sub["retailer"].nunique(),
                        "items": len(sub), "brand_list": ", ".join(sorted(sub["retailer"].unique())),
                        "examples": " | ".join(sub["name"].head(3))})
    agg = pd.DataFrame(agg).sort_values(["brands", "items"], ascending=False)
    out = Path("data/processed/retailer_attributes.csv")
    agg.to_csv(out, index=False, encoding="utf-8-sig")

    print(f"\nВсего новинок: {len(df)} ({df['retailer'].value_counts().to_dict()})")
    print("\n=== Признаки, которые повторяются у нескольких брендов ===")
    for _, r in agg[agg["brands"] >= 2].iterrows():
        print(f"  {r['group']:<17} {r['attribute']:<12} брендов {r['brands']}  товаров {r['items']:>3}  ({r['brand_list']})")
    print(f"\nСнимок: {snap}\nСохранено: {out}")


if __name__ == "__main__":
    main()
