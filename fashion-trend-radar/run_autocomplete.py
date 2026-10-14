"""
Search suggestions (autocomplete) for chosen candidates from Google, YouTube
and Amazon US -- the public endpoints the search boxes call while you type.
Shows which concrete version of an item people are looking for
(colour, fabric, fit, occasion). ~20 requests per candidate, 1-2 s apart.
Output: data/processed/autocomplete.csv (one row per suggestion) and
        data/processed/autocomplete_summary.csv (top modifiers per candidate)
Usage: .venv/Scripts/python.exe run_autocomplete.py "roll neck sweater" "hoco dress" ...
"""
import random
import re
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
SUFFIXES = ["", " ", " for", " with", " women", " outfit", " in"]
COLORS = {"black", "white", "cream", "ivory", "beige", "brown", "chocolate", "camel", "tan", "grey", "gray",
          "navy", "blue", "red", "burgundy", "wine", "pink", "green", "olive", "sage", "purple", "lilac",
          "yellow", "gold", "silver", "orange", "leopard", "oatmeal"}
STOP = {"for", "with", "in", "women", "womens", "woman", "the", "a", "and", "of", "to", "on", "near", "me",
        "outfit", "outfits"}


def google(q, client="firefox", ds=None):
    params = {"client": client, "q": q, "hl": "en", "gl": "us"}
    if ds:
        params["ds"] = ds
    r = requests.get("https://suggestqueries.google.com/complete/search", params=params, headers=UA, timeout=20)
    r.raise_for_status()
    if client == "firefox":
        return r.json()[1]
    # youtube client returns JSONP: window.google.ac.h([...])
    m = re.search(r"\((.*)\)\s*$", r.text, re.S)
    import json
    return [s[0] for s in json.loads(m.group(1))[1]] if m else []


def amazon(q):
    r = requests.get("https://completion.amazon.com/api/2017/suggestions",
                     params={"mid": "ATVPDKIKX0DER", "alias": "aps", "prefix": q, "limit": 11},
                     headers=UA, timeout=20)
    r.raise_for_status()
    return [s["value"] for s in r.json().get("suggestions", [])]


SOURCES = {
    "google": lambda q: google(q),
    "youtube": lambda q: google(q, client="youtube", ds="yt"),
    "amazon": amazon,
}


def modifiers(cand, suggestion):
    base = set(cand.lower().split())
    words = re.findall(r"[a-z0-9']+", suggestion.lower())
    return [w for w in words if w not in base and w not in STOP and len(w) > 2]


def main():
    cands = sys.argv[1:] or pd.read_csv("config/candidates.csv")["candidate"].tolist()   # was a hardcoded old list (23.09 fix)
    rows = []
    for cand in cands:
        for src, fn in SOURCES.items():
            seen = set()
            for suf in SUFFIXES:
                q = cand + suf
                try:
                    sugg = fn(q)
                except Exception as e:
                    print(f"  {src} «{q}»: ошибка {e}")
                    sugg = []
                for s in sugg:
                    if s.lower() not in seen and cand.split()[0] in s.lower():
                        seen.add(s.lower())
                        rows.append({"date": str(date.today()), "candidate": cand, "source": src,
                                     "typed": q, "suggestion": s.lower()})
                time.sleep(random.uniform(1.0, 2.2))
            print(f"{cand} · {src}: {len(seen)} подсказок")

    df = pd.DataFrame(rows)
    out = Path("data/processed/autocomplete.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")

    summary = []
    for cand, g in df.groupby("candidate"):
        cnt = Counter()
        srcs = {}
        for _, r in g.iterrows():
            for w in set(modifiers(cand, r["suggestion"])):
                cnt[w] += 1
                srcs.setdefault(w, set()).add(r["source"])
        top = [(w, n, ",".join(sorted(srcs[w]))) for w, n in cnt.most_common(40)]
        colors = [w for w, _, _ in top if w in COLORS]
        summary.append({
            "candidate": cand,
            "suggestions": len(g),
            "top_modifiers": " | ".join(f"{w} ({n}; {s})" for w, n, s in top[:15]),
            "in_all_sources": ", ".join(w for w, _, s in top if s.count(",") == 2),
            "colors": ", ".join(colors[:8]),
            "amazon_examples": " | ".join(g[g["source"] == "amazon"]["suggestion"].head(6)),
        })
    sm = pd.DataFrame(summary)
    sm.to_csv("data/processed/autocomplete_summary.csv", index=False, encoding="utf-8-sig")
    for _, r in sm.iterrows():
        print(f"\n== {r['candidate']} ({r['suggestions']} подсказок)")
        print("  чаще всего дописывают:", r["top_modifiers"])
        print("  во всех трёх источниках:", r["in_all_sources"] or "—")
        print("  цвета:", r["colors"] or "—")
        print("  Amazon:", r["amazon_examples"])
    print(f"\nСохранено: {out}, data/processed/autocomplete_summary.csv")


if __name__ == "__main__":
    main()
