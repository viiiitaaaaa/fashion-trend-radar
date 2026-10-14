"""
Candidate discovery channel #2: TikTok Creative Center trending hashtags
(US), read from the same GetHashtagList responses the page itself loads,
in Dolphin profile 3 (logged in), at human volume (one page view per
period, scrolling). Server-side industry filter isn't reproducible yet, so
we pull the full top-100 and keep: TikTok-tagged Apparel & Accessories
(22000000000) OR hashtags containing fashion words.
Output: data/processed/candidates_tiktok_cc.csv
"""
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, r"C:\Users\User\dolphin_anty")
from dolphin import DolphinLocal, start_with_retry  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PROFILE = 859648353
APPAREL = "22000000000"
PERIODS = [90]  # minimum 90 days per user rule: stable trends, not weekly spikes
FASHION_WORDS = [
    "outfit", "ootd", "fashion", "style", "skirt", "dress", "sweater", "cardigan",
    "jeans", "denim", "pants", "trouser", "top", "blouse", "jacket", "coat",
    "knit", "lace", "boots", "fit", "wear", "aesthetic", "core", "look",
]
RAW = Path("data/raw/tiktok_cc")
RAW.mkdir(parents=True, exist_ok=True)


def url_for(period):
    return ("https://ads.tiktok.com/business/creativecenter/inspiration/popular/"
            f"hashtag/pc/en?period={period}&region=US")


def collect_period(page, period):
    pages = {}

    def on_resp(resp):
        if "GetHashtagList" in resp.url:
            try:
                j = resp.json()
                pages[j["pagination"]["page"]] = j
            except Exception:
                pass

    def rewrite(route, request):
        # The page's URL param for long windows isn't honoured, so set the
        # window on the page's own request body instead.
        try:
            body = json.loads(request.post_data or "{}")
            body["timeRange"] = period
            route.continue_(post_data=json.dumps(body))
        except Exception:
            route.continue_()

    page.route(re.compile(r".*GetHashtagList.*"), rewrite)
    page.on("response", on_resp)
    page.goto(url_for(7), timeout=90000, wait_until="domcontentloaded")
    time.sleep(8)
    for _ in range(25):
        page.mouse.wheel(0, 1200)
        time.sleep(1.8)
        last = max(pages) if pages else 0
        if pages and not pages[last]["pagination"].get("hasMore", True):
            break
        # some layouts need an explicit "View more" click
        try:
            btn = page.get_by_text("View more", exact=False)
            if btn.count():
                btn.first.click(timeout=3000)
                time.sleep(2)
        except Exception:
            pass
    page.remove_listener("response", on_resp)
    page.unroute(re.compile(r".*GetHashtagList.*"))

    rows = []
    for pno in sorted(pages):
        for it in pages[pno].get("items", []):
            curve = [p["value"] for p in it.get("popularityCurve", [])]
            rows.append({
                "period_days": period,
                "rank": int(it.get("rankIndex") or 0),
                "hashtag": it.get("hashtagName"),
                "industry_ids": "|".join(it.get("industryIDs") or []),
                "posts": int(it.get("publishCnt") or 0),
                "views": int(it.get("vv") or 0),
                "curve": curve,
                "curve_last_vs_first": (curve[-1] - curve[0]) if curve else None,
            })
    return rows, pages


def main():
    api = DolphinLocal(port=DolphinLocal.discover() or 3001)
    auto = start_with_retry(api, PROFILE, no_tabs=True)["automation"]
    all_rows = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"ws://127.0.0.1:{auto['port']}{auto['wsEndpoint']}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        for period in PERIODS:
            rows, pages = collect_period(page, period)
            (RAW / f"hashtags_{period}d_{date.today()}.json").write_text(
                json.dumps(pages, ensure_ascii=False), encoding="utf-8")
            print(f"period {period}d: {len(rows)} hashtags ({len(pages)} pages)")
            all_rows += rows
            time.sleep(6)
        page.close()

    df = pd.DataFrame(all_rows)
    if df.empty:
        print("Ничего не собрано.")
        return
    df["is_apparel"] = df["industry_ids"].str.contains(APPAREL, na=False)
    df["has_fashion_word"] = df["hashtag"].str.lower().apply(
        lambda h: any(w in (h or "") for w in FASHION_WORDS))
    fashion = df[df["is_apparel"] | df["has_fashion_word"]].copy()

    out = Path("data/processed/candidates_tiktok_cc.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    fashion.to_csv(out, index=False, encoding="utf-8-sig")

    print(f"\nВсего хэштегов: {len(df)}, из них про моду: {len(fashion)}")
    for _, r in fashion.sort_values(["period_days", "rank"]).iterrows():
        tag = "APPAREL" if r["is_apparel"] else "word"
        print(f"  [{r['period_days']}d #{r['rank']}] #{r['hashtag']}  posts={r['posts']} views={r['views']} ({tag})")
    print(f"Сохранено: {out}")


if __name__ == "__main__":
    main()
