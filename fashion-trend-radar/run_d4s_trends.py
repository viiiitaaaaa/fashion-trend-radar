"""
Who searches and where (DataForSEO Trends via treg.to, US, last 12 months) for all candidates (<=5 per request):
  subregion_interests  -> interest by US state (0-100)          $0.0024 per 5 keywords
  demography           -> age groups and gender (0-100)         $0.0024 per 5 keywords
Runs only by hand.  --from-raw re-reads today's saved answers (no new charge).
Output: data/processed/d4s_states.csv, data/processed/d4s_demography.csv
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import dotenv_values

env = dotenv_values(".env")
H = {"X-Treg-Token": env["TREG_TOKEN"], "X-Treg-Org": env.get("TREG_ORG", "vi"), "Content-Type": "application/json"}
RAW = Path("data/raw/treg")
EPS = {"subregion": "dataforseo.x.keywords-data-dataforseo-trends-subregion-interests-live",
       "demography": "dataforseo.x.keywords-data-dataforseo-trends-demography-live"}


def fetch(kind, kws):
    body = [{"keywords": kws, "location_code": 2840, "type": "web", "time_range": "past_12_months"}]
    r = requests.post(f"https://treg.to/call/{EPS[kind]}", headers=H, data=json.dumps(body), timeout=180)
    print(f"{kind}: HTTP {r.status_code}, ${int(r.headers.get('X-Treg-Cost-Micro') or 0) / 1e6:.4f}")
    r.raise_for_status()
    d = r.json()
    (RAW / f"{datetime.now():%Y%m%d_%H%M%S}_d4s_{kind}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def items(d):
    return [i for t in (d.get("tasks") or []) for res in (t.get("result") or []) for i in (res.get("items") or [])]


def main():
    from_raw = "--from-raw" in sys.argv
    cands = pd.read_csv("config/candidates.csv")["candidate"].tolist()
    states, demo = [], []
    for i in range(0, len(cands), 5):
        kws = cands[i:i + 5]
        for kind in EPS:
            if from_raw:
                f = sorted(RAW.glob(f"*_d4s_{kind}.json"))
                d = json.loads(f[-1].read_text(encoding="utf-8"))
            else:
                d = fetch(kind, kws)
            for it in items(d):
                if kind == "subregion":
                    for k in it.get("interests") or []:
                        for v in k.get("values") or []:
                            states.append({"candidate": k["keyword"], "state": v["geo_name"], "value": v["value"]})
                else:
                    for group, rows in (it.get("demography") or {}).items():
                        for k in rows:
                            for v in k.get("values") or []:
                                demo.append({"candidate": k["keyword"], "group": group, "type": v["type"], "value": v["value"]})
    out = Path("data/processed")
    pd.DataFrame(states).assign(date=str(date.today())).to_csv(out / "d4s_states.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(demo).assign(date=str(date.today())).to_csv(out / "d4s_demography.csv", index=False, encoding="utf-8-sig")
    print(f"Сохранено: d4s_states.csv ({len(states)}), d4s_demography.csv ({len(demo)})")


if __name__ == "__main__":
    main()
