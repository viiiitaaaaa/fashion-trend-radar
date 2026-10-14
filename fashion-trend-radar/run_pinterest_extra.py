"""
Pinterest Trends through the logged-in business account (open Dolphin profile 3, no API key), for the radar
candidates + every concrete item from pinterest_discovery.csv:
  1) 2-year weekly curve   -> /metrics/      (days=730, aggregation=2)
  2) who searches          -> /demographics/ (age 18-24 ... 65+, female/male share, last 90 days)
Endpoints and params are the page's own (found in its JS 23.09).
Output: data/processed/pinterest_discovery_curves.json  {term: {"dates": [...], "values": [...]}}
        data/processed/pinterest_demographics.csv
Usage: .venv/Scripts/python.exe run_pinterest_extra.py
"""
import json
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

from run_retailers import cdp_endpoint

BATCH = 10
CURVES = Path("data/processed/pinterest_discovery_curves.json")
DEMO = Path("data/processed/pinterest_demographics.csv")
AGES = ["18-24", "25-34", "35-44", "45-49", "50-54", "55-64", "65+"]


def get(page, path, params):
    url = f"/{path}/?" + urllib.parse.urlencode(params, safe=",")
    st, body = page.evaluate("async u => { const r = await fetch(u); return [r.status, await r.text()] }", url)
    if st != 200:
        raise RuntimeError(f"{path} HTTP {st}")
    return json.loads(body)


def terms_to_fetch():
    cand = pd.read_csv("config/candidates.csv")
    col = "pinterest_term" if "pinterest_term" in cand else "candidate"
    ours = [t for t in cand[col].fillna(cand["candidate"]).tolist() if t]
    # ALL concrete items of the discovery file (pinterest_discovery() already hides 18-24 items — that needs these ages)
    from build_dashboard import PIN_THEME
    d = pd.read_csv("data/processed/pinterest_discovery.csv")
    items = d[~d["term"].str.contains(PIN_THEME, case=False, regex=True)]["term"].tolist()
    return list(dict.fromkeys(ours + items))


def main():
    terms = terms_to_fetch()
    curves = json.loads(CURVES.read_text(encoding="utf-8")) if CURVES.exists() else {}
    demo_rows = []
    with sync_playwright() as p:
        page = p.chromium.connect_over_cdp(cdp_endpoint()).contexts[0].new_page()
        try:
            page.goto("https://trends.pinterest.com/?country=US", timeout=60000)
            time.sleep(8)
            end = str(date.today() - timedelta(days=3))
            try:
                end = get(page, "latest_available_date", {}).get("date") or end
            except Exception:
                pass
            print(f"{len(terms)} вещей, конец периода {end}")
            for i in range(0, len(terms), BATCH):
                batch = terms[i:i + BATCH]
                try:
                    data = get(page, "metrics", {"terms": ",".join(batch), "country": "US", "end_date": end, "days": 730,
                                                 "aggregation": 2, "normalize_against_group": "false", "predicted_days": 0})
                    for item in data:
                        cs = item.get("counts") or []
                        curves[item["term"]] = {"dates": [c.get("date") for c in cs], "values": [c.get("normalizedCount") for c in cs]}
                except Exception as e:
                    print(f"  кривые {batch[0]}…: {e}")
                time.sleep(1.2)
                try:
                    dist = get(page, "demographics", {"terms": ",".join(batch), "country": "US", "end_date": end, "days": 90})
                    for term, d in (dist.get("term_distributions") or {}).items():
                        a, g = d.get("age_distribution") or {}, d.get("gender_distribution") or {}
                        demo_rows.append({"term": term, **{f"age_{k}": a.get(k) for k in AGES},
                                          "female": g.get("female"), "male": g.get("male")})
                except Exception as e:
                    print(f"  возраст {batch[0]}…: {e}")
                time.sleep(1.2)
                print(f"  {min(i + BATCH, len(terms))}/{len(terms)}")
        finally:
            page.close()
    CURVES.write_text(json.dumps(curves, ensure_ascii=False), encoding="utf-8")
    df = pd.DataFrame(demo_rows)
    if DEMO.exists() and not df.empty:   # merge: never drop ages of terms not in this run
        old = pd.read_csv(DEMO)
        df = pd.concat([old[~old["term"].isin(df["term"])].drop(columns=["main_age"], errors="ignore"), df], ignore_index=True)
    if not df.empty:
        top = df[[f"age_{k}" for k in AGES]].astype(float)
        df["main_age"] = top.idxmax(axis=1).str.replace("age_", "")
        df.to_csv(DEMO, index=False, encoding="utf-8-sig")
    print(f"Кривых: {len(curves)}, возраст/пол: {len(df)} -> {CURVES}, {DEMO}")


if __name__ == "__main__":
    main()
