"""
Competitors' ads in the US from the public Meta Ad Library website (the API gives only political ads outside the EU),
read in the open Dolphin profile 3 at a human pace. Per candidate: how many active ads, how many advertisers,
how many ads have been running 30+ days (long-running ad = it pays off), top advertisers. Stops after 2 blocks.
Output: data/processed/meta_web.csv, data/processed/meta_web_ads.csv
Usage: .venv/Scripts/python.exe run_meta_adlib_web.py ["candidate" ...]
"""
import random
import re
import sys
import time
import urllib.parse
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

from run_retailers import cdp_endpoint

OUT, OUT_A = Path("data/processed/meta_web.csv"), Path("data/processed/meta_web_ads.csv")
URL = ("https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={country}&q={q}"
       "&search_type=keyword_unordered&media_type=all")


def parse(text):
    total = re.search(r"~?([\d,]+)\s+results?", text)
    ads = []
    for block in text.split("Library ID:")[1:]:
        start = re.search(r"Started running on ([A-Z][a-z]{2} \d{1,2}, \d{4})", block)
        who = re.search(r"See ad details\s*\n?\s*(.+?)\s*\n?\s*Sponsored", block, re.S)
        lib = re.match(r"\s*(\d+)", block)
        d = datetime.strptime(start.group(1), "%b %d, %Y").date() if start else None
        ads.append({"library_id": lib.group(1) if lib else "", "advertiser": (who.group(1).strip().split("\n")[-1] if who else "")[:80],
                    "start": str(d) if d else "", "days_running": (date.today() - d).days if d else None})
    return (int(total.group(1).replace(",", "")) if total else len(ads)), ads


def save(rows, path):
    new = pd.DataFrame(rows)
    if new.empty:
        return
    if path.exists():
        old = pd.read_csv(path)
        new = pd.concat([old[~old["candidate"].isin(new["candidate"])], new], ignore_index=True)
    new.to_csv(path, index=False, encoding="utf-8-sig")


def main():
    # --country GB: the same site for another country (24.09.2026: the EU API needs an ID check the user can't do)
    args = sys.argv[1:]
    country = args[args.index("--country") + 1] if "--country" in args else "US"
    args = [a for i, a in enumerate(args) if a != "--country" and (i == 0 or args[i - 1] != "--country")]
    global OUT, OUT_A
    if country != "US":
        OUT, OUT_A = Path(f"data/processed/meta_web_{country.lower()}.csv"), Path(f"data/processed/meta_web_ads_{country.lower()}.csv")
    cands = args or pd.read_csv("config/candidates.csv")["candidate"].tolist()
    summary, rows, blocked = [], [], 0
    with sync_playwright() as p:
        page = p.chromium.connect_over_cdp(cdp_endpoint()).contexts[0].new_page()
        try:
            for c in cands:
                q = c.replace(" women", "")
                page.goto(URL.format(country=country, q=urllib.parse.quote(q)), timeout=90000, wait_until="domcontentloaded")
                time.sleep(random.uniform(8, 11))
                text = page.inner_text("body")
                if "login" in page.url or re.search(r"captcha|security check|temporarily blocked", text[:3000], re.I):
                    blocked += 1
                    print(f"  {c}: Facebook просит вход/проверку ({blocked}/2)")
                    if blocked >= 2:
                        break
                    continue
                for _ in range(4):
                    page.mouse.wheel(0, 2200)
                    time.sleep(random.uniform(1.5, 2.5))
                total, ads = parse(page.inner_text("body"))
                for a in ads:
                    a.update(candidate=c, date=str(date.today()))
                rows += ads
                adv = Counter(a["advertiser"] for a in ads if a["advertiser"])
                summary.append({"candidate": c, "query": q, "active_ads": total, "sampled": len(ads),
                                "advertisers": len(adv), "running_30d_plus": sum(1 for a in ads if (a["days_running"] or 0) >= 30),
                                "top_advertisers": " | ".join(f"{n} ({k})" for n, k in adv.most_common(4)), "date": str(date.today())})
                s = summary[-1]
                print(f"  {c:<22} активных ~{s['active_ads']:>5}, в выборке {s['sampled']:>3}, рекламодателей {s['advertisers']:>3}, "
                      f"идут 30+ дней {s['running_30d_plus']:>3} | {s['top_advertisers'][:70]}")
                time.sleep(random.uniform(6, 10))
        finally:
            page.close()
    save(summary, OUT)
    save(rows, OUT_A)
    print(f"Сохранено: {OUT}, {OUT_A}")


if __name__ == "__main__":
    main()
