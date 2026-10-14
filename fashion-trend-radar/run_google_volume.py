"""
Real Google search volume in the US (DataForSEO via treg.to): monthly searches for the last 12+ months,
CPC and competition, for ALL candidates in one call ($0.09 per call, up to 1000 keywords). Runs only by hand.
Output: data/processed/google_volume.csv (one row per candidate: avg monthly volume, yoy, cpc)
        data/processed/google_volume_monthly.csv (candidate, month, searches)
"""
import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import dotenv_values

env = dotenv_values(".env")
H = {"X-Treg-Token": env["TREG_TOKEN"], "X-Treg-Org": env.get("TREG_ORG", "vi"), "Content-Type": "application/json"}
ENDPOINT = "dataforseo.google.keywords.volume"
RAW = Path("data/raw/treg")


def main():
    cands = pd.read_csv("config/candidates.csv")["candidate"].tolist()
    body = [{"keywords": cands, "location_code": 2840, "language_code": "en"}]   # 2840 = United States
    r = requests.post(f"https://treg.to/call/{ENDPOINT}", headers=H, data=json.dumps(body), timeout=180)
    cost = int(r.headers.get("X-Treg-Cost-Micro") or 0) / 1e6
    d = r.json()
    (RAW / f"{datetime.now():%Y%m%d_%H%M%S}_{ENDPOINT}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    print(f"HTTP {r.status_code}, стоимость ${cost:.4f}")
    r.raise_for_status()

    items = [x for t in (d.get("tasks") or []) for x in (t.get("result") or []) if isinstance(x, dict)]
    rows, monthly = [], []
    for x in items:
        kw = x.get("keyword")
        ms = sorted(x.get("monthly_searches") or [], key=lambda m: (m["year"], m["month"]))
        for m in ms:
            monthly.append({"candidate": kw, "month": f"{m['year']}-{m['month']:02d}", "searches": m.get("search_volume")})
        vals = [m.get("search_volume") or 0 for m in ms]
        last3, prev3 = vals[-3:], vals[-15:-12] if len(vals) >= 15 else []
        yoy = round((sum(last3) / sum(prev3) - 1) * 100, 1) if prev3 and sum(prev3) else None
        avg = sum(vals) / len(vals) if vals else None
        rows.append({"candidate": kw, "avg_monthly": x.get("search_volume"), "last_month": vals[-1] if vals else None,
                     "yoy_3m_pct": yoy,   # DataForSEO returns 12 months -> usually None
                     "last_vs_avg_pct": round((vals[-1] / avg - 1) * 100) if avg else None, "cpc": x.get("cpc"), "competition": x.get("competition"),
                     "months": len(vals), "date": str(date.today())})
        print(f"  {kw:<24} в среднем {x.get('search_volume')!s:>8}/мес, последний месяц {rows[-1]['last_month']!s:>8}, "
              f"3 мес к прошлому году {yoy}%, клик ${x.get('cpc')}")
    out = Path("data/processed")
    pd.DataFrame(rows).to_csv(out / "google_volume.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(monthly).to_csv(out / "google_volume_monthly.csv", index=False, encoding="utf-8-sig")
    print(f"Сохранено: google_volume.csv ({len(rows)} слов)")


if __name__ == "__main__":
    main()
