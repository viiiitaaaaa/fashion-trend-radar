"""
Pinterest Trends discovery through the logged-in business account (open Dolphin profile 3, no API key):
growing US search terms among WOMEN that contain a garment word, via the page's own /top_trends_filtered/.
Filter names are the page's own (found in its JS 23.09): keywordsToInclude, gender (2 = female),
ageBucket, l1InterestIds (948967005229 = women's fashion; ignored by this endpoint so far).
Output: data/processed/pinterest_discovery.csv — term, garment, wow/mom/yoy %, seasonality, volume index.
Usage: .venv/Scripts/python.exe run_pinterest_discovery.py
"""
import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

from run_retailers import cdp_endpoint

GARMENTS = ["sweater", "cardigan", "skirt", "coat", "jacket", "top", "dress", "boots", "pants", "jeans",
            "shirt", "vest", "blazer", "scarf", "knit", "trench", "leggings", "hoodie"]
PRESETS = {3: "growing", 1: "seasonal"}      # page tabs: growing trends / seasonal trends
RAW = Path("data/raw/pinterest_trends")
OUT = Path("data/processed/pinterest_discovery.csv")
NOT_CLOTHES = ("nail", "hair", "cake", "wallpaper", "drawing", "tattoo", "makeup", "decor", "recipe", "reference",
               "design", "costume", "guy", "adult", "ceremony", "stove", "cherry on top", "of many colors")


def pct(change):
    return round(change["value"] * 100) if change and change.get("value") is not None else None


def main():
    rows, dump = [], {}
    with sync_playwright() as p:
        page = p.chromium.connect_over_cdp(cdp_endpoint()).contexts[0].new_page()
        try:
            page.goto("https://trends.pinterest.com/?country=US", timeout=60000)
            time.sleep(8)
            end = page.evaluate("async () => (await fetch('/latest_available_date/')).text()")
            try:
                end = json.loads(end).get("date") or json.loads(end).get("latest_available_date")
            except Exception:
                end = None
            end = end or str(date.today() - timedelta(days=3))
            for preset, kind in PRESETS.items():
                for g in GARMENTS:
                    url = (f"/top_trends_filtered/?lookbackWindow=3&endDate={end}&rankingMethod=3&country=US"
                           f"&trendsPreset={preset}&numTermsToReturn=50&gender=2&keywordsToInclude={g}")
                    st, body = page.evaluate("async u => { const r = await fetch(u); return [r.status, await r.text()] }", url)
                    if st != 200:
                        print(f"  {kind}/{g}: ошибка {st}")
                        continue
                    vals = json.loads(body).get("values", [])
                    dump[f"{kind}/{g}"] = vals
                    for v in vals:
                        # keywordsToInclude matches substrings ("coat" -> "coating", "top" -> "stove top")
                        if any(w in v["term"] for w in NOT_CLOTHES) or not re.search(rf"\b{g}s?\b", v["term"]):
                            continue
                        rows.append({"term": v["term"], "garment": g, "list": kind,
                                     "wow": pct(v.get("wow_change")), "mom": pct(v.get("mom_change")),
                                     "yoy": pct(v.get("yoy_change")), "seasonality": round(v.get("seasonality_score") or 0, 2),
                                     "volume_idx": v.get("normalizedCount")})
                    print(f"  {kind}/{g}: {len(vals)}")
                    time.sleep(1.5)
        finally:
            page.close()
    RAW.joinpath(f"discovery_{date.today()}.json").write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    df = pd.DataFrame(rows).drop_duplicates("term").sort_values(["list", "yoy"], ascending=[True, False])
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"Сохранено {len(df)} запросов (женщины, США), конец периода {end} -> {OUT}")


if __name__ == "__main__":
    main()
