"""
Builds FashionCandidate objects from what the project ACTUALLY collects today
(Google Trends timeseries + raw TikTok videos) and runs them through
src/processors/fashion_score.py.

Honesty note (read before trusting a low score): Pinterest weekly/monthly/
yearly growth, Meta Ad Library, Amazon rank change, retailer confirmation,
supplier count, duplicate-listing count and sell price/cost are NOT collected
by this project yet (see TZ_trend_scoring.md rollout steps 2-6). Those inputs
stay at their dataclass defaults (0 / False), which pulls commercial_score,
uniqueness_score and margin_score toward zero regardless of the real trend.
Read google_score and tiktok_score as the only currently-trustworthy blocks;
treat fashion_score itself as a floor, not a verdict, until those collectors
exist.

TikTok buy-intent is approximated from the video DESCRIPTION/caption text
(the only text field this collector saves) with the keyword list from the
spec -- not from actual comment text, which isn't collected. Treat
tiktok_buy_intent_comments as a weak proxy.

Usage: .venv/Scripts/python.exe run_fashion_score.py
"""

import glob
import os
import statistics

import pandas as pd

from src.processors.fashion_score import FashionCandidate, calculate_fashion_score
from src.processors.seasonality import detect_seasonality
from src.processors.saturation import SaturationInput, calculate_saturation_penalty
from src.storage.files import save_csv

EXPORT_DIR = "data/exports"

BUY_INTENT_PATTERNS = [
    "where is", "where did you get", "where can i buy", "link",
    "need this", "i need this", "drop the link", "what is the brand",
    "what brand", "where from", "obsessed", "adding to cart", "take my money",
]


def _latest(prefix):
    files = sorted(glob.glob(os.path.join(EXPORT_DIR, f"{prefix}*.csv")))
    return files[-1] if files else None


def _has_buy_intent(text):
    text = (text or "").lower()
    return any(p in text for p in BUY_INTENT_PATTERNS)


def google_growth(values):
    """values: chronological weekly interest, oldest first."""
    clean = [v for v in values if v is not None and not (isinstance(v, float) and pd.isna(v))]
    if len(clean) < 16:
        return {"g7": 0.0, "g30": 0.0, "g90": 0.0, "recent": clean[-1] if clean else 0.0,
                 "recent_4w": 0.0, "same_4w_last_year": 0.0, "trailing_52w": 0.0}

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    def pct(cur, prev):
        return ((cur - prev) / prev * 100) if prev else 0.0

    last_1w, prev_1w = clean[-1], clean[-2] if len(clean) >= 2 else clean[-1]
    last_4w = avg(clean[-4:])
    prev_4w = avg(clean[-8:-4]) if len(clean) >= 8 else last_4w
    last_12w = avg(clean[-12:])
    prev_12w = avg(clean[-24:-12]) if len(clean) >= 24 else last_12w

    same_4w_last_year = avg(clean[-56:-52]) if len(clean) >= 56 else last_4w
    trailing_52w = avg(clean[-52:]) if len(clean) >= 52 else avg(clean)

    return {
        "g7": pct(last_1w, prev_1w),
        "g30": pct(last_4w, prev_4w),
        "g90": pct(last_12w, prev_12w),
        "recent": clean[-1],
        "recent_4w": last_4w,
        "same_4w_last_year": same_4w_last_year,
        "trailing_52w": trailing_52w,
    }


def main():
    trends_f = _latest("trends_summary_")
    ts_f = _latest("trends_timeseries_")
    tik_f = _latest("tiktok_videos_")

    if not trends_f or not ts_f:
        raise SystemExit("Нет trends_summary_*.csv / trends_timeseries_*.csv в data/exports")

    keywords_df = pd.read_csv(trends_f)
    ts = pd.read_csv(ts_f)
    tik = pd.read_csv(tik_f) if tik_f else pd.DataFrame()

    rows = []
    for _, krow in keywords_df.iterrows():
        kw = krow["keyword"]

        kw_ts = ts[ts["keyword"] == kw].sort_values(
            "date", key=lambda s: pd.to_datetime(s, errors="coerce")
        )
        g = google_growth(kw_ts["value"].tolist())

        # Separate penalty modules (src/processors/seasonality.py,
        # src/processors/saturation.py) -- computed once, passed in, never
        # re-derived inside calculate_fashion_score (avoids double-subtracting).
        seasonality = detect_seasonality(
            kw_ts.rename(columns={"value": "interest"})[["date", "interest"]]
        )
        # Only ~53 weeks of history are collected today (12-month Bright Data
        # series), detect_seasonality needs >=80 -- it honestly returns
        # NOT_ENOUGH_HISTORY / penalty 0.0 rather than guessing. Will start
        # producing real penalties once 2 years of snapshots accumulate.
        saturation = calculate_saturation_penalty(SaturationInput(keyword=kw))
        # SaturationInput left at defaults -- duplicate-listing/Meta Ads/
        # supplier data isn't collected yet (TZ steps 3-6), so this is
        # currently always LOW_SATURATION by construction, not a real read.

        kw_tik = tik[tik["keyword"] == kw] if not tik.empty else pd.DataFrame()
        if not kw_tik.empty:
            plays = kw_tik["plays"].dropna().tolist()
            eng = kw_tik["engagement_rate"].dropna().tolist()
            shares = kw_tik["shares"].dropna().tolist()
            saves = kw_tik["saves"].dropna().tolist()
            median_plays = statistics.median(plays) if plays else 0.0
            median_eng = statistics.median(eng) if eng else 0.0
            shares_per_1k = (statistics.median(shares) / median_plays * 1000) if median_plays else 0.0
            saves_per_1k = (statistics.median(saves) / median_plays * 1000) if median_plays else 0.0
            buy_intent = int(kw_tik["description"].apply(_has_buy_intent).sum())
            video_count = len(kw_tik)
            unique_creators = kw_tik["author"].nunique()
        else:
            median_plays = median_eng = shares_per_1k = saves_per_1k = 0.0
            buy_intent = video_count = unique_creators = 0

        candidate = FashionCandidate(
            keyword=kw,
            google_growth_7d=g["g7"],
            google_growth_30d=g["g30"],
            google_growth_90d=g["g90"],
            google_recent_interest=g["recent"],
            google_rising_queries_count=0,  # not collected -- see TZ step 2

            # Pinterest growth %/related-keywords not collected (only raw
            # pin scrape, not official Trends API) -- stays 0.
            pinterest_weekly_growth=0.0,
            pinterest_monthly_growth=0.0,
            pinterest_yearly_growth=0.0,
            pinterest_related_keywords_count=0,

            tiktok_video_count=video_count,
            tiktok_unique_creators=unique_creators,
            tiktok_views_median=median_plays,
            tiktok_engagement_rate=median_eng,
            tiktok_shares_per_1k_views=shares_per_1k,
            tiktok_saves_per_1k_views=saves_per_1k,
            tiktok_buy_intent_comments=buy_intent,

            # Not collected yet -- TZ steps 3-6.
            meta_active_ads=0, meta_oldest_ad_days=0, meta_unique_advertisers=0,
            amazon_rank_change_pct=0.0, retailer_confirmation_count=0,
            unique_product_angle=False, content_angles_count=0,
            supplier_count=0, duplicate_listing_count=0,
            sell_price=0.0, product_cost=0.0, shipping_cost=0.0,
        )

        result = calculate_fashion_score(
            candidate,
            seasonality_penalty=seasonality.penalty,
            saturation_penalty=saturation["saturation_penalty"],
        )
        result["category"] = krow.get("category")
        result["style"] = krow.get("style")
        result["seasonality_label"] = seasonality.label
        result["saturation_label"] = saturation["saturation_label"]
        rows.append(result)

    out = pd.DataFrame(rows).sort_values("fashion_score", ascending=False)
    save_csv(out, "data/reports/fashion_score.csv")

    print(out[["keyword", "fashion_score", "status", "google_score", "tiktok_score",
               "commercial_score", "uniqueness_score", "margin_score"]].to_string(index=False))
    print("\nC/U/M почти у всех 0 или низкие -- эти блоки ещё не собираются (см. TZ_trend_scoring.md).")
    print("Сохранено: data/reports/fashion_score.csv")


if __name__ == "__main__":
    main()
