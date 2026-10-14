"""
Competitors' ads for the radar candidates from the official Meta Ad Library API (/ads_archive).
Outside the EU/UK the API returns only political/social ads, so this collects ads DELIVERED IN THE EU/UK
(all ad types incl. clothing, under the EU Digital Services Act) — with reach by age and gender.
The user creates the access token herself (Graph API Explorer, her app) and puts it into .env as META_ACCESS_TOKEN;
with META_APP_ID + META_APP_SECRET in .env the script swaps a short token for a 60-day one.
Output: data/processed/meta_ads.csv (per candidate), data/processed/meta_ads_list.csv (ads)
Usage: .venv/Scripts/python.exe run_meta_ads.py ["candidate" ...]
"""
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import dotenv_values, set_key

ENV = Path(".env")
GRAPH = "https://graph.facebook.com/v23.0"
COUNTRIES = ["GB", "DE", "FR", "IT", "ES", "NL", "PL"]
FIELDS = ("id,page_name,page_id,ad_delivery_start_time,ad_delivery_stop_time,ad_creative_bodies,ad_creative_link_titles,"
          "ad_snapshot_url,publisher_platforms,eu_total_reach,age_country_gender_reach_breakdown,target_ages,target_gender")
OUT, OUT_L = Path("data/processed/meta_ads.csv"), Path("data/processed/meta_ads_list.csv")


def token():
    env = dotenv_values(ENV)
    t = env.get("META_ACCESS_TOKEN")
    if not t:
        raise SystemExit("Нет META_ACCESS_TOKEN в .env — создайте токен в Graph API Explorer и вставьте строку в .env")
    if env.get("META_APP_ID") and env.get("META_APP_SECRET") and not env.get("META_TOKEN_LONG"):
        r = requests.get(f"{GRAPH}/oauth/access_token", params={
            "grant_type": "fb_exchange_token", "client_id": env["META_APP_ID"], "client_secret": env["META_APP_SECRET"],
            "fb_exchange_token": t}, timeout=30)
        if r.ok and r.json().get("access_token"):
            t = r.json()["access_token"]
            set_key(str(ENV), "META_ACCESS_TOKEN", t)
            set_key(str(ENV), "META_TOKEN_LONG", str(date.today()))
            print("Токен продлён на ~60 дней.")
    return t


def ads(tok, term, pages=3):
    out, url = [], f"{GRAPH}/ads_archive"
    params = {"access_token": tok, "search_terms": term, "ad_type": "ALL", "ad_active_status": "ALL",
              "ad_reached_countries": str(COUNTRIES).replace("'", '"'), "fields": FIELDS, "limit": 100,
              "ad_delivery_date_min": str(date.today().replace(year=date.today().year - 1))}
    for _ in range(pages):
        r = requests.get(url, params=params, timeout=60)
        d = r.json()
        if "error" in d:
            raise RuntimeError(d["error"].get("message", str(d["error"]))[:200])
        out += d.get("data", [])
        url, params = (d.get("paging") or {}).get("next"), None
        if not url:
            break
        time.sleep(1)
    return out


def age28_share(ad):
    """Share of EU reach from people 28+ (35+ plus 7/10 of 25-34), like the radar's audience rule."""
    tot = old = 0
    for c in ad.get("age_country_gender_reach_breakdown") or []:
        for a in c.get("age_gender_breakdowns") or []:
            n = sum(a.get(k) or 0 for k in ("male", "female", "unknown"))
            tot += n
            rng = a.get("age_range", "")
            old += n * (0.7 if rng == "25-34" else 1 if rng and rng not in ("13-17", "18-24", "25-34") else 0)
    return round(old / tot * 100) if tot else None


def main():
    tok = token()
    cands = sys.argv[1:] or pd.read_csv("config/candidates.csv")["candidate"].tolist()
    summary, rows = [], []
    for c in cands:
        q = c.replace(" women", "")
        try:
            got = ads(tok, q)
        except RuntimeError as e:
            print(f"  {c}: {e}")
            if "token" in str(e).lower() or "session" in str(e).lower():
                raise SystemExit("Токен недействителен или истёк — создайте новый в Graph API Explorer.")
            continue
        now = datetime.now()
        for a in got:
            start = a.get("ad_delivery_start_time", "")[:10]
            rows.append({"candidate": c, "page": a.get("page_name"), "start": start,
                         "days_running": (now - datetime.fromisoformat(start)).days if start else None,
                         "active": not a.get("ad_delivery_stop_time"), "eu_reach": a.get("eu_total_reach"),
                         "aud28": age28_share(a), "text": " ".join(a.get("ad_creative_bodies") or [])[:200],
                         "snapshot": a.get("ad_snapshot_url"), "date": str(date.today())})
        mine = [r for r in rows if r["candidate"] == c]
        long_ = [r for r in mine if (r["days_running"] or 0) >= 30]
        a28 = [r["aud28"] for r in mine if r["aud28"] is not None]
        summary.append({"candidate": c, "query": q, "ads": len(mine), "advertisers": len({r["page"] for r in mine}),
                        "active": sum(r["active"] for r in mine), "running_30d_plus": len(long_),
                        "reach_total": sum(r["eu_reach"] or 0 for r in mine),
                        "aud28_median": int(pd.Series(a28).median()) if a28 else None, "date": str(date.today())})
        s = summary[-1]
        print(f"  {c:<22} объявлений {s['ads']:>3}, рекламодателей {s['advertisers']:>3}, идут 30+ дней {s['running_30d_plus']:>3}, 28+ ~{s['aud28_median']}%")
        time.sleep(1)
    for data, path in ((summary, OUT), (rows, OUT_L)):
        new = pd.DataFrame(data)
        if path.exists() and not new.empty:
            old = pd.read_csv(path)
            new = pd.concat([old[~old["candidate"].isin(new["candidate"])], new], ignore_index=True)
        if not new.empty:
            new.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Сохранено: {OUT}, {OUT_L}")


if __name__ == "__main__":
    main()
