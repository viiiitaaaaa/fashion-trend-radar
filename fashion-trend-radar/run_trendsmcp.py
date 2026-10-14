"""
TikTok (hashtag volume) and Amazon (search volume) curves from trendsmcp.ai for the radar.
Free plan: 90 days of weekly history, 100 requests/month -- one candidate costs 2 requests.
Runs only by hand (no schedule). Answers younger than 7 days are reused from data/raw/trendsmcp/.

    python run_trendsmcp.py                       # all candidates from config/candidates.csv
    python run_trendsmcp.py "plaid skirt" "bow top"

Output: data/processed/trendsmcp.csv -- one row per candidate x source:
  lift_pct -- latest period vs the one before it (TikTok: 14 vs 14 days, Amazon: month vs month).
              90 days is too short for a year-over-year check, so this is "rising right now"
              and includes the season. TikTok has data only for big hashtags (no_data is free).
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.clients import trendsmcp_client as tm

SOURCES = ["tiktok", "amazon"]
FRESH_DAYS = 7
OUT = Path("data/processed/trendsmcp.csv")


def cached(source: str, keyword: str):
    slug = f"get_time_series_{source}_{keyword}".replace(" ", "-")[:80]
    for p in sorted(tm.RAW.glob(f"*_{slug}.json"), reverse=True):
        if datetime.now() - datetime.strptime(p.name[:15], "%Y%m%d_%H%M%S") > timedelta(days=FRESH_DAYS):
            break
        data = json.loads(p.read_text(encoding="utf-8"))
        if tm.rows(data):
            return data
    return None


def fetch(source: str, phrase: str):
    """TikTok is keyed by hashtag: try the phrase, then the hashtag form (no spaces)."""
    tries = [phrase] + ([phrase.replace(" ", "")] if source == "tiktok" and " " in phrase else [])
    last_err = ""
    for kw in tries:
        data = cached(source, kw)
        if data is None:
            try:
                data = tm.time_series(source, kw)
            except RuntimeError as e:   # no_data etc. -- failed calls don't use the quota
                last_err = str(e)[:120]
                continue
        if tm.rows(data):
            return kw, tm.rows(data), ""
        last_err = "empty answer"
    return tries[-1], [], last_err


def summarize(candidate, source, kw, rows, err):
    rows = sorted(rows, key=lambda r: r["date"])
    v = [float(r["value"]) for r in rows]
    dates = pd.to_datetime([r["date"] for r in rows])
    # Sources differ in step: TikTok daily (30 days), Amazon monthly (with volume), Google weekly.
    # Compare the latest period with the one right before it: 14 days / 1 month / 4 weeks.
    step = pd.Series(dates).diff().dt.days.median() if len(v) > 1 else None
    grain, n = ("month", 1) if step and step >= 25 else ("day", 14) if step and step < 6 else ("week", 4)
    mean = lambda xs: sum(xs) / len(xs)
    lift = None
    if len(v) >= 2 * n and mean(v[-2 * n:-n]):
        lift = round((mean(v[-n:]) / mean(v[-2 * n:-n]) - 1) * 100, 1)
    return {
        "candidate": candidate, "source": source, "keyword_used": kw, "grain": grain if v else "",
        "points": len(v),
        "nonzero_share": round(sum(1 for x in v if x > 0) / len(v), 2) if v else None,
        "lift_pct": lift,
        "last_volume": rows[-1].get("volume") if rows else None,   # Amazon: searches that month
        "last_date": rows[-1]["date"] if rows else "",
        "series": ";".join(f"{x:g}" for x in v),
        "error": err,
    }


def main(candidates):
    todo = [(c, s) for c in candidates for s in SOURCES]
    need = sum(1 for c, s in todo if cached(s, c) is None and cached(s, c.replace(" ", "")) is None)
    left = tm.FREE_MONTHLY - tm.used_this_month()
    print(f"Кандидатов: {len(candidates)}, новых запросов нужно до {need}, осталось в квоте: {left}")
    if need > left:
        raise SystemExit("Квоты не хватит — передайте меньше кандидатов аргументами.")

    rows = []
    for c, s in todo:
        kw, r, err = fetch(s, c)
        rows.append(summarize(c, s, kw, r, err))
        x = rows[-1]
        vol = f"объём={x['last_volume']:,}" if x["last_volume"] else ""
        print(f"  {c:<24} {s:<7} точек={x['points']:<3} ({x['grain']}) рост={x['lift_pct']}%  {vol}  {err[:40]}")

    new = pd.DataFrame(rows)
    if OUT.exists():   # keep other candidates' rows from earlier partial runs
        old = pd.read_csv(OUT)
        old = old[~old.set_index(["candidate", "source"]).index.isin(new.set_index(["candidate", "source"]).index)]
        new = pd.concat([old, new], ignore_index=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(OUT, index=False)
    print(f"\nСохранено: {OUT}. Потрачено в этом месяце: {tm.used_this_month()}/{tm.FREE_MONTHLY}")


if __name__ == "__main__":
    main(sys.argv[1:] or pd.read_csv("config/candidates.csv")["candidate"].tolist())
