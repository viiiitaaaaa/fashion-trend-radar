"""
Builds the cross-channel candidate table from the latest outputs of every
channel collector (no new scraping here -- run the collectors first).
Output: data/reports/radar_candidates.csv
"""
import glob
from pathlib import Path

import pandas as pd

from radar_curves import _pinterest_series as pinterest_series, use_short_phrase
from src.processors.candidate_matrix import build_matrix


def latest(pattern):
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def load(pattern, reader, **kw):
    f = latest(pattern)
    return reader(f, **kw) if f else pd.DataFrame()


def main():
    cfg = pd.read_csv("config/candidates.csv", keep_default_na=False)
    candidates = cfg["candidate"].tolist()
    # manual_decision / manual_reason: the user's own call (e.g. an early trend the channels can't see yet)
    manual = {r.candidate: (r.manual_decision, r.manual_reason) for r in cfg.itertuples()
              if "manual_decision" in cfg and r.manual_decision in ("TEST", "WATCH", "LATER", "REJECT")}
    # season_months: the user's own season calendar, e.g. "5,6,7,8" (overrides the Google calendar)
    season_override = {r.candidate: {int(m) for m in str(r.season_months).split(",") if m.strip()}
                       for r in cfg.itertuples() if "season_months" in cfg and str(r.season_months).strip()}

    google_rising = load("data/processed/candidates_google_rising.csv", pd.read_csv)
    hist_root = Path("data/normalized/google_trends")
    google_history = pd.read_parquet(hist_root) if hist_root.exists() else pd.DataFrame()
    if not google_history.empty:
        # weekly runs append new part files -- keep one point per week
        google_history = (google_history.sort_values("date")
                          .drop_duplicates(subset=["date", "keyword", "region"], keep="last"))
    yt_root = Path("data/normalized/google_trends_youtube")
    youtube_history = pd.read_parquet(yt_root) if yt_root.exists() else pd.DataFrame()
    if not youtube_history.empty:
        youtube_history = (youtube_history.sort_values("date")
                           .drop_duplicates(subset=["date", "keyword", "region"], keep="last"))
        youtube_history = use_short_phrase(youtube_history)
    sh_root = Path("data/normalized/google_trends_shopping")
    shopping_history = pd.read_parquet(sh_root) if sh_root.exists() else pd.DataFrame()
    if not shopping_history.empty:
        shopping_history = (shopping_history.sort_values("date")
                            .drop_duplicates(subset=["date", "keyword", "region"], keep="last"))
    pinterest = load("data/processed/pinterest_metrics.csv", pd.read_csv)
    pinterest = pinterest[pinterest["source"] == "our_candidates"] if not pinterest.empty else pinterest
    tiktok = load("data/processed/candidates_tiktok_cc.csv", pd.read_csv)
    amazon = load("data/normalized/amazon/amazon_*.parquet", pd.read_parquet)
    retailers = load("data/normalized/retailers/retailers_*.parquet", pd.read_parquet)

    pin_series = {term: [v for _, v in pts] for term, pts in pinterest_series().items()}

    m = build_matrix(candidates, google_rising, google_history, pinterest, tiktok, amazon, retailers,
                     pinterest_series=pin_series, youtube_history=youtube_history,
                     youtube_api=load("data/processed/youtube_api.csv", pd.read_csv),
                     trendsmcp=load("data/processed/trendsmcp.csv", pd.read_csv),
                     shopping_history=shopping_history,
                     amazon_bought=load("data/processed/amazon_bought.csv", pd.read_csv),
                     tiktok_tags=load("data/processed/tiktok_tags.csv", pd.read_csv),
                     instagram_tags=load("data/processed/instagram_tags.csv", pd.read_csv),
                     manual=manual, season_override=season_override)

    out = Path("data/reports/radar_candidates.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    m.to_csv(out, index=False, encoding="utf-8-sig")

    mark = lambda b: "✓" if b else "·"
    print(f"{'кандидат':<24} G  P  Y  T  A  R  I  итог  решение  | Pinterest год  | заметки")
    for _, r in m.iterrows():
        yoy = "" if pd.isna(r["pin_yoy_pct"]) else f"{r['pin_yoy_pct']:+.0f}%"
        note = []
        if r["season_months"]:
            note.append(f"сезон {r['season_months']}")
        if r["later_reason"]:
            note.append(f"ПОЗЖЕ: {r['later_reason']}")
        if r["manual_reason"]:
            note.append(f"РУЧНОЕ: {r['manual_reason']} (авто: {r['auto_decision']})")
        if r["seasonal_flag"]:
            note.append("СЕЗОН")
        if r["retailer_list"]:
            note.append(f"бренды: {r['retailer_list']}")
        if r["amazon_items"]:
            note.append(f"Amazon {r['amazon_items']} шт, ~${r['amazon_median_price']}")
        if pd.notna(r["amazon_monthly_searches"]):
            note.append(f"поиск Amazon {r['amazon_monthly_searches']:,.0f}/мес ({r['amazon_mcp_lift_pct']:+.0f}%)")
        if pd.notna(r["amazon_bought_sum"]):
            note.append(f"купили ≥{r['amazon_bought_sum']:,.0f}/мес")
        if pd.notna(r["tt_us_fresh"]):
            note.append(f"TikTok #{r['tt_hashtag']}: США свежих {r['tt_us_fresh']:.0f}/{r['tt_us_sampled']:.0f}")
        if pd.notna(r["tiktok_mcp_lift_pct"]):
            note.append(f"TikTok {r['tiktok_mcp_lift_pct']:+.0f}% за 2 нед")
        print(f"{r['candidate']:<24} {mark(r['check_google'])}  {mark(r['check_pinterest'])}  "
              f"{mark(r['check_youtube'])}  {mark(r['check_tiktok'])}  {mark(r['check_amazon'])}  "
              f"{mark(r['check_retailers'])}  {mark(r['check_instagram'])}  {r['checks_passed']}/7  {r['decision']:<7}  | {yoy:>6}         | {'; '.join(note)}")
    print(f"\nСохранено: {out}")


if __name__ == "__main__":
    main()
