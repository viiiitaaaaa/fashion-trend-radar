"""
Which VERSION of each item people search for: all autocomplete suggestions (run_autocomplete.py, free) for the
current candidates -> real US Google monthly volume for each phrase in ONE DataForSEO call via treg ($0.09 for up
to 1000 phrases). Shows the colours / cuts / materials worth sourcing. Runs only by hand, once.
Output: data/processed/variant_volumes.csv (candidate, phrase, volume, cpc)
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
NOISE = ("men", "mens", "kids", "toddler", "girls", "boys", "pattern", "knitting", "crochet", "how to", "diy")


def main():
    cands = pd.read_csv("config/candidates.csv")["candidate"].tolist()
    a = pd.read_csv("data/processed/autocomplete.csv")
    a = a[a["candidate"].isin(cands)].copy()
    a["phrase"] = a["suggestion"].str.lower().str.strip()
    # keep women's-fashion versions of the item: must contain the item's main words, drop kids / men / DIY
    core = {c: [w for w in c.split() if w not in ("women", "womens")] for c in cands}
    a = a[a.apply(lambda r: all(w in r["phrase"] for w in core[r["candidate"]])
                  and not any(f" {n} " in f" {r['phrase']} " for n in NOISE), axis=1)]
    # DataForSEO rejects the whole task if any phrase has >10 words or odd symbols (Amazon gives full product titles)
    a = a[a["phrase"].str.split().str.len().le(10) & a["phrase"].str.len().le(80)
          & a["phrase"].str.fullmatch(r"[a-z0-9 '&-]+")]
    pairs = a.drop_duplicates(["candidate", "phrase"])[["candidate", "phrase"]]
    phrases = sorted(set(pairs["phrase"]))[:1000]
    print(f"фраз для проверки: {len(phrases)}")
    body = [{"keywords": phrases, "location_code": 2840, "language_code": "en"}]
    r = requests.post(f"https://treg.to/call/{ENDPOINT}", headers=H, data=json.dumps(body), timeout=300)
    print(f"HTTP {r.status_code}, стоимость ${int(r.headers.get('X-Treg-Cost-Micro') or 0) / 1e6:.4f}")
    d = r.json()
    Path("data/raw/treg", f"{datetime.now():%Y%m%d_%H%M%S}_variant_volumes.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    r.raise_for_status()
    vol = {x["keyword"]: (x.get("search_volume"), x.get("cpc"))
           for t in d.get("tasks") or [] for x in (t.get("result") or []) if isinstance(x, dict)}
    pairs["volume"] = pairs["phrase"].map(lambda p: (vol.get(p) or (None, None))[0])
    pairs["cpc"] = pairs["phrase"].map(lambda p: (vol.get(p) or (None, None))[1])
    pairs["date"] = str(date.today())
    pairs = pairs.sort_values(["candidate", "volume"], ascending=[True, False], na_position="last")
    pairs.to_csv("data/processed/variant_volumes.csv", index=False, encoding="utf-8-sig")
    for c, g in pairs.groupby("candidate"):
        top = g.dropna(subset=["volume"]).head(8)
        print(f"\n{c}: " + " | ".join(f"{p} {int(v):,}" for p, v in zip(top["phrase"], top["volume"])))
    print("\nСохранено: data/processed/variant_volumes.csv")


if __name__ == "__main__":
    main()
