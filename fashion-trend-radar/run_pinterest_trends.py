"""
Channel #4: Pinterest Trends (business login, Dolphin profile 3).
  1) discovery: terms the trends page itself shows as growing (US)
  2) validation: wow/mom/yoy growth for OUR candidates (from Google rising,
     TikTok CC and Amazon new releases), via the same /metrics/ endpoint
     the page uses, called from inside the logged-in page, small batches.
Output: data/processed/pinterest_metrics.csv
"""
import json
import random
import sys
import time
import urllib.parse
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, r"C:\Users\User\dolphin_anty")
from dolphin import DolphinLocal, start_with_retry  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PROFILE = 859648353
URL = "https://trends.pinterest.com/?country=US"
RAW = Path("data/raw/pinterest_trends")
RAW.mkdir(parents=True, exist_ok=True)
BATCH = 10

# Candidates surfaced so far by the other channels (not invented):
# Google rising (fall/bandana cardigan, roll neck sweater, hoco dress,
# womens fall jacket), earlier radar keywords, Amazon new releases
# (lace trim, satin/faux leather/faux suede midi skirt, sweater dress,
# flannel plaid shirt, cable knit), TikTok CC (bow, fall outfit inspo).
CANDIDATES = [
    "plaid skirt", "plaid mini skirt", "funnel neck sweater", "chunky sweater",
    "faux fur coat", "tennis skirt",
    "fall cardigan", "bandana cardigan", "roll neck sweater", "hoco dress",
    "womens fall jacket",
    "lace trim top", "lace trim skirt", "satin midi skirt", "faux leather midi skirt",
    "faux suede skirt", "sweater dress", "wrap sweater dress", "flannel shirt women",
    "cable knit sweater",
    "bow top", "fall outfit inspo",
]

FASHION_WORDS = ["outfit", "dress", "skirt", "sweater", "cardigan", "top", "jeans",
                 "pants", "jacket", "coat", "boots", "style", "fashion", "knit", "lace"]


PAGE_PARAMS = {"end_date": None}  # filled from the page's own metrics call


def fetch_metrics(page, terms):
    params = {
        "terms": ",".join(terms),
        "country": "US",
        "end_date": PAGE_PARAMS["end_date"] or str(date.today()),
        "days": "730",
        "aggregation": "2",
        "normalize_against_group": "false",
        "predicted_days": "0",
    }
    qs = urllib.parse.urlencode(params, safe=",")
    js = """async (url) => { const r = await fetch(url, {credentials: 'include'});
                             return {status: r.status, body: await r.text()}; }"""
    res = page.evaluate(js, f"https://trends.pinterest.com/metrics/?{qs}")
    if res["status"] != 200:
        raise RuntimeError(f"metrics HTTP {res['status']}")
    return json.loads(res["body"])


def to_rows(terms, data, source):
    rows = []
    for term, item in zip(terms, data):
        g = (item or {}).get("growth_rates") or {}
        counts = (item or {}).get("counts") or []
        # Pinterest returns growth as fractions (0.3 = +30%) -> convert to %.
        pct = lambda v: round(v * 100, 1) if isinstance(v, (int, float)) else None
        vals = [c.get("normalizedCount") for c in counts]
        yoy = pct(g.get("yoy_change"))
        if yoy is None and len(vals) >= 56:
            recent, last_year = sum(vals[-4:]) / 4, sum(vals[-56:-52]) / 4
            yoy = round((recent - last_year) / last_year * 100, 1) if last_year else None
        rows.append({
            "term": item.get("term", term) if isinstance(item, dict) else term,
            "source": source,
            "wow_pct": pct(g.get("wow_change")),
            "mom_pct": pct(g.get("mom_change")),
            "yoy_pct": yoy,
            "weeks": len(counts),
            "last_norm": counts[-1].get("normalizedCount") if counts else None,
        })
    return rows


def main():
    api = DolphinLocal(port=DolphinLocal.discover() or 3001)
    auto = start_with_retry(api, PROFILE, no_tabs=True)["automation"]
    discovered = []
    rows = []
    raw_dump = {}
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"ws://127.0.0.1:{auto['port']}{auto['wsEndpoint']}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()

        def on_resp(resp):
            if "/metrics/?terms=" in resp.url:
                q = urllib.parse.parse_qs(urllib.parse.urlparse(resp.url).query)
                terms = q.get("terms", [""])[0].split(",")
                if q.get("end_date"):
                    PAGE_PARAMS["end_date"] = q["end_date"][0]
                try:
                    discovered.extend(to_rows(terms, resp.json(), "pinterest_page"))
                except Exception:
                    pass

        page.on("response", on_resp)
        page.goto(URL, timeout=90000, wait_until="domcontentloaded")
        time.sleep(10)
        for _ in range(4):
            page.mouse.wheel(0, 1000)
            time.sleep(1.5)
        page.remove_listener("response", on_resp)

        for i in range(0, len(CANDIDATES), BATCH):
            batch = CANDIDATES[i:i + BATCH]
            data = fetch_metrics(page, batch)
            raw_dump[",".join(batch)] = data
            rows += to_rows(batch, data, "our_candidates")
            print(f"validated {i + len(batch)}/{len(CANDIDATES)}")
            time.sleep(random.uniform(4, 8))
        page.close()

    (RAW / f"metrics_{date.today()}.json").write_text(json.dumps(raw_dump, ensure_ascii=False), encoding="utf-8")

    df = pd.DataFrame(discovered + rows).drop_duplicates(subset=["term", "source"])
    df["is_fashion"] = df["term"].str.lower().apply(lambda t: any(w in t for w in FASHION_WORDS))
    out = Path("data/processed/pinterest_metrics.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")

    ours = df[df["source"] == "our_candidates"].sort_values("mom_pct", ascending=False)
    missing = [t for t in CANDIDATES if t not in set(ours["term"])]
    print("\n=== Наши кандидаты на Pinterest (рост, %) ===")
    for _, r in ours.iterrows():
        print(f"  {r['term']:<26} неделя {r['wow_pct']!s:>7}  месяц {r['mom_pct']!s:>7}  год {r['yoy_pct']!s:>7}")
    print(f"\nPinterest не отслеживает (слишком мало поисков): {', '.join(missing)}")
    disc = df[(df["source"] == "pinterest_page") & df["is_fashion"]]
    print(f"\n=== Растущие модные слова с главной Pinterest Trends: {len(disc)} ===")
    for _, r in disc.sort_values("mom_pct", ascending=False).head(15).iterrows():
        print(f"  {r['term']:<32} месяц {r['mom_pct']!s:>7}  год {r['yoy_pct']!s:>7}")
    print(f"Сохранено: {out}")


if __name__ == "__main__":
    main()
