"""
Cross-channel candidate matrix: one row per trend candidate, one column per
independent "witness" (Google, Pinterest, TikTok, Amazon, retailers), plus a
checks-passed count and a decision. Implements the TZ rule "min 4 of 6
checks" on 6 automated checks: Google, Pinterest, YouTube search, TikTok,
Amazon, retailers (content potential stays manual).

Matching a candidate phrase to items (Amazon titles, retailer names,
TikTok hashtags, Google rising queries) uses the fashion taxonomy:
  - if the candidate has a category (skirt/top/...), the item must share it;
  - AND share at least one non-category attribute (pattern/material/
    neckline/silhouette/detail/audience), or -- when the candidate has no
    such attribute (e.g. "hoco dress") -- contain its remaining words.
"""
from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass

import pandas as pd

from src.processors.fashion_taxonomy import extract_fashion_features, normalize_text

STOP = {"women", "womens", "woman", "for", "the", "a", "and", "with", "outfit", "outfits", "inspo",
        # season words are SEO filler in marketplace titles ("Fall Outfits 2026"), not attributes
        "fall", "autumn", "winter", "spring", "summer", "2025", "2026", "2027"}


@dataclass
class CandidateSpec:
    phrase: str
    categories: set
    attrs: set          # {(group, label)} excluding category
    words: set          # leftover significant words


def spec_for(phrase: str) -> CandidateSpec:
    f = extract_fashion_features(phrase)
    cats = set(f.get("category", []))
    attrs = {(g, l) for g, ls in f.items() if g != "category" for l in ls}
    cat_words = {"skirt", "dress", "top", "sweater", "cardigan", "jacket", "coat",
                 "jeans", "pants", "shirt", "blouse", "set", "trousers"}
    words = set(normalize_text(phrase).split()) - STOP - cat_words
    return CandidateSpec(phrase, cats, attrs, words)


def matches(spec: CandidateSpec, text: str) -> bool:
    t = normalize_text(text)
    f = extract_fashion_features(t)
    if spec.categories and not (spec.categories & set(f.get("category", []))):
        return False
    if spec.attrs:
        item_attrs = {(g, l) for g, ls in f.items() if g != "category" for l in ls}
        return bool(spec.attrs & item_attrs)
    if spec.words:
        return all(re.search(rf"\b{re.escape(w)}", t) for w in spec.words)
    # No attributes and no leftover words: only meaningful for a two-category
    # item like "sweater dress" (knitwear + dress) -- require ALL categories.
    if len(spec.categories) >= 2:
        return spec.categories <= set(f.get("category", []))
    return False  # too generic ("cardigan" alone) to count as evidence


def hashtag_matches(spec: CandidateSpec, hashtag: str) -> bool:
    """Hashtags have no spaces (#falloutfitinspo) -- match on raw substrings."""
    h = (hashtag or "").lower()
    keys = {w for w in spec.words if len(w) >= 3}
    for g, l in spec.attrs:
        keys.add(l.replace("_", ""))
    return bool(keys) and any(k in h for k in keys)


WINDOW = 8          # weeks compared against the same weeks a year earlier
SEASON_LIFT = 20    # % rise last year in these weeks that marks a recurring season
MIN_YOY = 5         # % growth for every growth check (user decision 22.09.2026: was 15)
# Audience 28+ (user 23.09.2026): share of interest from people 28 and older = 35+ plus 7 of the 10 years of 25-34.
# Google (DataForSEO demography) is closer to buyers and is used first; Pinterest skews young for every item
# (median 46%, quartiles 43-51%), so for Pinterest-only items the bar is "younger than a typical Pinterest item".
AUD28_MIN_GOOGLE = 50
AUD28_MIN_PINTEREST = 43
_AUD = {}


def audience_28(phrase):
    """-> (share of interest from people 28+ in %, source) or (None, "")."""
    if not _AUD:
        f = Path("data/processed/d4s_demography.csv")
        if f.exists():
            g = pd.read_csv(f)
            g = g[g["group"] == "age"].pivot(index="candidate", columns="type", values="value").fillna(0)
            old = [c for c in g.columns if c not in ("18-24", "25-34")]
            share = (0.7 * g.get("25-34", 0) + g[old].sum(axis=1)) / g.sum(axis=1) * 100
            _AUD.update({k: (round(v), "Google") for k, v in share.dropna().items()})
        f = Path("data/processed/pinterest_demographics.csv")
        if f.exists():
            d = pd.read_csv(f).drop_duplicates("term").set_index("term")
            ages = [c for c in d.columns if c.startswith("age_")]
            old = [c for c in ages if c not in ("age_18-24", "age_25-34")]
            share = (0.7 * d["age_25-34"] + d[old].sum(axis=1)) / d[ages].sum(axis=1) * 100
            for k, v in share.dropna().items():
                _AUD.setdefault(k, (round(v), "Pinterest"))
        _AUD.setdefault("__loaded__", (None, ""))
    return _AUD.get(phrase, (None, ""))


# Amazon search volume (Trends MCP) doesn't know some phrases -> the closest wording it knows (checked 23.09)
MCP_MAX_AGE_DAYS = 62   # Trends MCP monthly data older than ~2 months is stale
AMAZON_SEARCH_ALIAS = {"roll neck sweater": "turtleneck sweater"}
MIN_NONZERO = 0.5   # share of weeks with data; below this the series is too sparse to judge
TT_MIN_FRESH = 5          # TikTok check: >= 5 US videos under our hashtag posted in the last 30 days
TT_MIN_FRESH_SHARE = 0.4  # ... and they are >= 40% of the US videos TikTok returns for the tag
IG_MIN_PER_DAY = 1.0      # Instagram check: >= 1 post a day under our hashtag ...
IG_MAX_AGE_DAYS = 7       # ... and the newest post is at most a week old
TEST_MIN, WATCH_MIN = 5, 3   # of 7 checks (user 23.09.2026): 5-7 test, 3-4 watch, 0-2 reject


def window_stats(values: list, w: int = WINDOW) -> dict | None:
    """Two-year comparison on weekly values (oldest first):
      yoy_pct   -- mean of the last w weeks vs the same w weeks a year earlier
      lift_now  -- last w weeks vs the w weeks before them (this year's rise)
      lift_prev -- the same, one year earlier (did these weeks rise last year too?)
    Averaging w weeks keeps a single spiky week from deciding the check."""
    v = [float(x) for x in values if x is not None and pd.notna(x)]
    if len(v) < 52 + 2 * w:
        return None
    # Low-volume phrases come back as mostly zeros (0 -> 12 reads as +1000%): not evidence
    if sum(1 for x in v if x > 0) / len(v) < MIN_NONZERO:
        return None
    mean = lambda xs: sum(xs) / len(xs)
    now, now_before = mean(v[-w:]), mean(v[-2 * w:-w])
    prev, prev_before = mean(v[-52 - w:-52]), mean(v[-52 - 2 * w:-52 - w])
    pct = lambda a, b: round((a - b) / b * 100, 1) if b else None
    return {"yoy_pct": pct(now, prev), "lift_now": pct(now, now_before), "lift_prev": pct(prev, prev_before)}


MIN_SEASON_WEEKS = 8   # user rule: seasonal items are fine, but the season must last >= 2 months

# Second track (user decision 22.09.2026, on plaid mini skirt): an item that does not grow
# year over year but has big, non-shrinking demand is not a REJECT -- it is "спрос есть".
STEADY_SEARCHES = 5000   # Amazon searches per month (trendsmcp)
STEADY_ITEMS = 5         # or this many matching items in Amazon best sellers / new releases
STEADY_BOUGHT = 1000     # or Amazon search page 1 shows >= this many bought in the past month
STEADY_MIN_YOY = -10     # Pinterest may dip this much and still count as "not shrinking"


def steady_demand(r: dict) -> bool:
    big = ((r.get("amazon_monthly_searches") or 0) >= STEADY_SEARCHES
           or (r.get("amazon_items") or 0) >= STEADY_ITEMS
           or (r.get("amazon_bought_sum") or 0) >= STEADY_BOUGHT)
    pin_ok = r.get("pin_yoy_pct") is None or r["pin_yoy_pct"] >= STEADY_MIN_YOY
    amz_ok = r.get("amazon_mcp_lift_pct") is None or r["amazon_mcp_lift_pct"] >= 0
    return bool(big and pin_ok and amz_ok)


def season_weeks(values: list) -> tuple[int, bool] | None:
    """How many weeks the demand season lasts: around each year's peak (2 years of weekly
    data, 3-week smoothing), count contiguous weeks at >= half the peak; take the longest.
    Returns (weeks, all_open) -- all_open means every season ran into the edge of the data
    (still going / started before it), so a short number is a lower bound, not a verdict.
    Measured over the whole series, not split per year: autumn seasons start in September,
    exactly where a per-year split would cut them."""
    v = [float(x) for x in values if x is not None and pd.notna(x)][-104:]
    if len(v) < 100 or sum(1 for x in v if x > 0) / len(v) < MIN_NONZERO:
        return None
    v = [sum(v[max(0, i - 1):i + 2]) / len(v[max(0, i - 1):i + 2]) for i in range(len(v))]
    n = len(v)
    runs = []
    for lo, hi in ((0, n // 2), (n // 2, n)):
        p = max(range(lo, hi), key=lambda i: v[i])
        thr, l, r = v[p] * 0.5, p, p
        while l > 0 and v[l - 1] >= thr:
            l -= 1
        while r < n - 1 and v[r + 1] >= thr:
            r += 1
        runs.append((r - l + 1, l == 0 or r == n - 1))
    return max(w for w, _ in runs), all(open_ for _, open_ in runs)


MONTHS_RU = "янв фев мар апр май июн июл авг сен окт ноя дек".split()
SOON_MONTHS = 2     # «текущий или предстоящий сезон»: this month and the next two
# User 23.09.2026: «мы продаём вещи на осенне-зимний сезон» -> an item fits if its season touches Sep–Feb
TARGET_SEASON = {9, 10, 11, 12, 1, 2}
TARGET_LABEL = "осень–зима (сен–фев)"


def season_calendar(dates: list, values: list) -> set | None:
    """Months of the season from the CLEAN year (104..52 weeks ago; spring 2026 Google glitch excluded):
    3-week smoothing, months where interest >= half of that year's peak. 10+ months = all year."""
    pts = [(str(d)[:10], float(v)) for d, v in zip(dates, values) if v is not None and pd.notna(v)]
    if len(pts) < 100:
        return None
    year = pts[-104:-52]
    vals = [v for _, v in year]
    if sum(1 for v in vals if v > 0) / len(vals) < MIN_NONZERO:
        return None
    sm = [sum(vals[max(0, i - 1):i + 2]) / len(vals[max(0, i - 1):i + 2]) for i in range(len(vals))]
    peak = max(sm)
    return {int(year[i][0][5:7]) for i in range(len(sm)) if peak and sm[i] >= peak * 0.5} or None


def months_label(months: set | None) -> str:
    if not months:
        return ""
    if len(months) >= 10:
        return "круглый год"
    # contiguous ranges, wrapping over December -> January
    ms = sorted(months)
    runs, start, prev = [], ms[0], ms[0]
    for m in ms[1:] + [None]:
        if m != (prev % 12) + 1:
            runs.append((start, prev))
            start = m
        prev = m if m else prev
    if len(runs) > 1 and runs[0][0] == 1 and runs[-1][1] == 12:
        runs = [(runs[-1][0], runs[0][1])] + runs[1:-1]
    return ", ".join(MONTHS_RU[a - 1] if a == b else f"{MONTHS_RU[a - 1]}–{MONTHS_RU[b - 1]}" for a, b in runs)


def in_season_soon(months: set | None, today_month: int) -> bool:
    """Fits our selling season: the item's season overlaps the target (autumn-winter) season.
    No calendar / all-year -> can't say it's off-season, so True. (today_month kept for the call signature.)"""
    if not months or len(months) >= 10:
        return True
    return bool(months & TARGET_SEASON)


AHEAD_WEEKS = 8     # user 22.09.2026: a season that starts within ~2 months must be considered


def season_ahead(values: list) -> float | None:
    """Last year's rise right after this point: mean of the 8 weeks that followed «now» a year ago
    vs the 4 weeks around «now» a year ago, in %. Positive and big = the season is about to start."""
    v = [float(x) for x in values if x is not None and pd.notna(x)]
    if len(v) < 60 or sum(1 for x in v if x > 0) / len(v) < MIN_NONZERO:
        return None
    mean = lambda xs: sum(xs) / len(xs)
    before, after = mean(v[-56:-52]), mean(v[-52:-52 + AHEAD_WEEKS])
    return round((after - before) / before * 100, 1) if before else None


MIN_GROWING_QUARTERS = 3   # of the last 4 quarters, each vs the same quarter a year earlier


def quarterly_growth(values: list) -> list | None:
    """Growth of each of the last 4 quarters (13 weeks) vs the same quarter a year earlier, oldest first."""
    v = [float(x) for x in values if x is not None and pd.notna(x)][-104:]
    if len(v) < 104 or sum(1 for x in v if x > 0) / len(v) < MIN_NONZERO:
        return None
    mean = lambda xs: sum(xs) / len(xs)
    out = []
    for i in range(3, -1, -1):
        now = v[len(v) - 13 * (i + 1):len(v) - 13 * i]
        prev = v[len(v) - 52 - 13 * (i + 1):len(v) - 52 - 13 * i]
        out.append(round((mean(now) - mean(prev)) / mean(prev) * 100, 1) if mean(prev) else None)
    return out


def is_stable_growth(st: dict | None, quarters: list | None) -> bool:
    """User rule: only steadily growing items. Last 8 weeks AND at least 3 of the last 4
    quarters above the same period a year earlier by MIN_YOY. Judged on Pinterest only:
    Google Trends has a simultaneous spike in Mar-May 2026 across almost every keyword
    (13 of 19 peak in April, incl. sweaters and fall jackets) -- a data artefact that
    fakes long-window growth."""
    if not st or not quarters or st["yoy_pct"] is None:
        return False
    return (st["yoy_pct"] >= MIN_YOY
            and sum(1 for q in quarters if q is not None and q >= MIN_YOY) >= MIN_GROWING_QUARTERS)


def is_seasonal(st: dict | None) -> bool:
    """Same weeks rose last year as well, and this year is not clearly higher -> the season repeating."""
    return bool(st and st["lift_prev"] is not None and st["yoy_pct"] is not None
                and st["lift_prev"] >= SEASON_LIFT and st["yoy_pct"] < MIN_YOY)


def build_matrix(
    candidates: list[str],
    google_rising: pd.DataFrame,      # keyword, value
    google_history: pd.DataFrame,     # date, keyword, interest, is_partial (2y)
    pinterest: pd.DataFrame,          # term, wow_pct, mom_pct, yoy_pct
    tiktok: pd.DataFrame,             # hashtag, posts, views
    amazon: pd.DataFrame,             # list, category, title
    retailers: pd.DataFrame,          # retailer, name
    pinterest_series: dict | None = None,   # term -> weekly values, 2y, oldest first
    youtube_history: pd.DataFrame | None = None,  # same shape as google_history, YouTube search
    youtube_api: pd.DataFrame | None = None,      # run_youtube_api.py output, one row per candidate
    trendsmcp: pd.DataFrame | None = None,        # run_trendsmcp.py output: candidate, source, lift_pct, ...
    shopping_history: pd.DataFrame | None = None, # same shape as google_history, Google Shopping (gprop=froogle)
    amazon_bought: pd.DataFrame | None = None,    # run_extra_signals.py --amazon: candidate, bought_sum, ...
    tiktok_tags: pd.DataFrame | None = None,      # run_tiktok_tags.py: hashtag totals + US videos in the last 30 days
    instagram_tags: pd.DataFrame | None = None,   # run_instagram_tags.py: posts per day under our hashtag (worldwide)
    manual: dict | None = None,                   # candidate -> (decision, reason): user's own call, shown as such
    season_override: dict | None = None,          # candidate -> set of months, when the user knows the season better
    today_month: int | None = None,
) -> pd.DataFrame:
    manual = manual or {}
    season_override = season_override or {}
    tt = tiktok_tags.set_index("candidate") if tiktok_tags is not None and not tiktok_tags.empty else pd.DataFrame()
    igt = instagram_tags.set_index("candidate") if instagram_tags is not None and not instagram_tags.empty else pd.DataFrame()
    if today_month is None:
        from datetime import date
        today_month = date.today().month
    bought = amazon_bought.set_index("candidate") if amazon_bought is not None and not amazon_bought.empty else pd.DataFrame()
    yt_api = youtube_api.set_index("candidate") if youtube_api is not None and not youtube_api.empty else pd.DataFrame()
    mcp = {}
    if trendsmcp is not None and not trendsmcp.empty:
        mcp = {(c, s): row for (c, s), row in trendsmcp.set_index(["candidate", "source"]).iterrows()}

    def mcp_lift(phrase, source):
        """trendsmcp curve: latest period vs the one before (90 days only, so no year-over-year).
        Sparse curves (mostly zeros) are not evidence, same rule as window_stats."""
        m = mcp.get((phrase, source))
        if m is None or pd.isna(m["lift_pct"]) or (pd.notna(m["nonzero_share"]) and m["nonzero_share"] < MIN_NONZERO):
            return None, None
        # 23.09.2026: for rare phrases Trends MCP returns an old window (cashmere beanie: Dec–Mar) — not current demand
        if pd.notna(m.get("last_date")) and pd.Timestamp(m["last_date"]) < pd.Timestamp.today() - pd.Timedelta(days=MCP_MAX_AGE_DAYS):
            return None, None
        return m["lift_pct"], (m["last_volume"] if pd.notna(m["last_volume"]) else None)
    rows = []
    pin = pinterest.set_index("term") if not pinterest.empty else pd.DataFrame()
    pinterest_series = pinterest_series or {}
    for phrase in candidates:
        s = spec_for(phrase)
        r = {"candidate": phrase}

        # Google: rising related query OR growth over the same 8 weeks last year
        g_hits = google_rising[google_rising["keyword"].apply(lambda k: matches(s, k))] if not google_rising.empty else google_rising
        r["google_rising_hits"] = len(g_hits)
        r["google_rising_top"] = " | ".join(f"{k} (+{int(v)}%)" for k, v in zip(g_hits["keyword"].head(2), g_hits["value"].head(2))) if len(g_hits) else ""
        g_st = None
        if not google_history.empty:
            h = google_history[google_history["keyword"] == phrase]
            g_st = window_stats(h[~h["is_partial"].astype(bool)].sort_values("date")["interest"].tolist())
        r["google_yoy_pct"] = g_st["yoy_pct"] if g_st else None
        r["google_season_lift_prev"] = g_st["lift_prev"] if g_st else None
        # Google Shopping removed 24.09.2026 (user: «там редко ищут» — mostly zeros for our items)
        r["google_shop_yoy_pct"] = None
        # +1..3% over 8 weeks is noise, not growth -- same bar as Pinterest
        r["check_google"] = (bool(len(g_hits))
                             or (r["google_yoy_pct"] is not None and r["google_yoy_pct"] >= MIN_YOY))

        # Pinterest: grew vs the same 8 weeks last year (not just the season)
        p_st = window_stats(pinterest_series[phrase]) if phrase in pinterest_series else None
        p = pin.loc[phrase] if phrase in pin.index else {}
        r["pin_mom_pct"] = p.get("mom_pct") if len(p) else None
        r["pin_yoy_1w_pct"] = p.get("yoy_pct") if len(p) else None      # Pinterest's own single-week number
        r["pin_yoy_pct"] = p_st["yoy_pct"] if p_st else None
        r["pin_season_lift_prev"] = p_st["lift_prev"] if p_st else None
        r["check_pinterest"] = r["pin_yoy_pct"] is not None and r["pin_yoy_pct"] >= MIN_YOY
        pq = quarterly_growth(pinterest_series[phrase]) if phrase in pinterest_series else None
        r["pin_quarters"] = " | ".join("—" if q is None else f"{q:+.0f}%" for q in pq) if pq else ""
        r["stable_growth"] = is_stable_growth(p_st, pq)

        # YouTube search ("how to wear ..."): same 8-week comparison as Google
        y_st = None
        if youtube_history is not None and not youtube_history.empty:
            h = youtube_history[youtube_history["keyword"] == phrase]
            y_st = window_stats(h[~h["is_partial"].astype(bool)].sort_values("date")["interest"].tolist())
        r["youtube_yoy_pct"] = y_st["yoy_pct"] if y_st else None
        # YouTube API: views of videos from the last 90 days vs the same 90 days a year ago.
        # Last year's videos had a year longer to collect views, so growth here is conservative.
        a = yt_api.loc[phrase] if phrase in yt_api.index else None
        r["yt_views_yoy_pct"] = a["yt_views_yoy_pct"] if a is not None and pd.notna(a["yt_views_yoy_pct"]) else None
        r["yt_views_90d"] = int(a["yt_views_90d"]) if a is not None else None
        r["yt_intent_comments"] = int(a["yt_intent_comments"]) if a is not None else None
        r["yt_comments_read"] = int(a["yt_comments_read"]) if a is not None else None
        r["yt_intent_examples"] = a["yt_intent_examples"] if a is not None and pd.notna(a["yt_intent_examples"]) else ""
        r["check_youtube"] = ((r["youtube_yoy_pct"] is not None and r["youtube_yoy_pct"] >= MIN_YOY)
                              or (r["yt_views_yoy_pct"] is not None and r["yt_views_yoy_pct"] >= MIN_YOY))

        # Season, judged on two years: Google Trends first (user 22.09.2026: «ориентируемся на Google Trends»),
        # Pinterest if Google has no usable series. 8-week windows in Jul-Sep are clear of the spring-2026 Google glitch.
        r["seasonal_flag"] = is_seasonal(g_st) if g_st else is_seasonal(p_st)

        # Season length: short event peaks (homecoming dress) don't fit the business
        g_vals, g_dates = [], []
        if not google_history.empty:
            h = google_history[google_history["keyword"] == phrase]
            h = h[~h["is_partial"].astype(bool)].sort_values("date")
            g_vals, g_dates = h["interest"].tolist(), h["date"].tolist()
        # Season calendar (user 22.09.2026: «ориентируемся на Google Trends», текущий или предстоящий сезон)
        cal = season_override.get(phrase) or season_calendar(g_dates, g_vals)
        r["season_months"] = months_label(cal)
        r["season_source"] = "вручную" if phrase in season_override else ("Google" if cal else "")
        r["in_season"] = in_season_soon(cal, today_month)
        sw = (season_weeks(pinterest_series[phrase]) if phrase in pinterest_series else None) or season_weeks(g_vals)
        r["season_weeks"] = sw[0] if sw else None
        r["short_season"] = bool(sw and sw[0] < MIN_SEASON_WEEKS and not sw[1])
        # Season about to start: Google Trends first (user's reference), Pinterest if Google has no series
        ahead = season_ahead(g_vals)
        ahead_yoy = r["google_yoy_pct"]
        if ahead is None and phrase in pinterest_series:
            ahead, ahead_yoy = season_ahead(pinterest_series[phrase]), r["pin_yoy_pct"]
        r["season_ahead_pct"] = ahead
        r["season_soon"] = bool(ahead is not None and ahead >= SEASON_LIFT
                                and (ahead_yoy is None or ahead_yoy >= STEADY_MIN_YOY))

        # TikTok: fashion hashtag in the 90-day top list, OR the hashtag's volume rising (trendsmcp)
        t_hits = tiktok[tiktok["hashtag"].apply(lambda h: hashtag_matches(s, h))] if not tiktok.empty else tiktok
        r["tiktok_hashtags"] = " ".join("#" + h for h in t_hits["hashtag"].head(3)) if len(t_hits) else ""
        r["tiktok_mcp_lift_pct"], _ = mcp_lift(phrase, "tiktok")
        # Our own hashtag in the US (treg/TikHub): is it alive right now?
        t = tt.loc[phrase] if phrase in tt.index else None
        num = lambda x: int(x) if x is not None and pd.notna(x) else None
        r["tt_hashtag"] = t["hashtag"] if t is not None else ""
        r["tt_total_videos"] = num(t["total_videos"]) if t is not None else None
        r["tt_total_views"] = num(t["total_views"]) if t is not None else None
        r["tt_us_sampled"] = num(t["us_videos_sampled"]) if t is not None else None
        r["tt_us_fresh"] = num(t["us_fresh_30d"]) if t is not None else None
        tt_alive = bool(r["tt_us_fresh"] and r["tt_us_sampled"]
                        and r["tt_us_fresh"] >= TT_MIN_FRESH
                        and r["tt_us_fresh"] / r["tt_us_sampled"] >= TT_MIN_FRESH_SHARE)
        r["check_tiktok"] = (bool(len(t_hits)) or tt_alive
                             or (r["tiktok_mcp_lift_pct"] is not None and r["tiktok_mcp_lift_pct"] >= MIN_YOY))

        # Amazon: >=2 matching items in new releases / best sellers, OR searches rising month over month (trendsmcp)
        a_hits = amazon[amazon["title"].fillna("").apply(lambda t: matches(s, t))] if not amazon.empty else amazon
        r["amazon_items"] = len(a_hits)
        r["amazon_new_releases"] = int((a_hits["list"] == "new_releases").sum()) if len(a_hits) else 0
        r["amazon_median_price"] = round(float(a_hits["price"].median()), 2) if len(a_hits) and a_hits["price"].notna().any() else None
        b = bought.loc[phrase] if phrase in bought.index else None
        r["amazon_bought_sum"] = int(b["bought_sum"]) if b is not None else None
        r["amazon_bought_items"] = int(b["items_with_bought"]) if b is not None else None
        r["amazon_mcp_lift_pct"], vol = mcp_lift(phrase, "amazon")
        r["amazon_search_phrase"] = phrase
        if not vol and phrase in AMAZON_SEARCH_ALIAS:   # Trends MCP doesn't know the phrase -> the closest one it knows
            r["amazon_mcp_lift_pct"], vol = mcp_lift(AMAZON_SEARCH_ALIAS[phrase], "amazon")
            r["amazon_search_phrase"] = AMAZON_SEARCH_ALIAS[phrase]
        r["amazon_monthly_searches"] = int(vol) if vol else None
        r["check_amazon"] = len(a_hits) >= 2 or (r["amazon_mcp_lift_pct"] is not None
                                                  and r["amazon_mcp_lift_pct"] >= MIN_YOY)

        # Retailers: >=2 brands releasing it
        re_hits = retailers[retailers["name"].fillna("").apply(lambda n: matches(s, n))] if not retailers.empty else retailers
        r["retailer_brands"] = int(re_hits["retailer"].nunique()) if len(re_hits) else 0
        r["retailer_list"] = ", ".join(sorted(re_hits["retailer"].unique())) if len(re_hits) else ""
        r["check_retailers"] = r["retailer_brands"] >= 2

        # Instagram (7th witness, user 23.09.2026): our hashtag gets >= 1 post a day and the newest post is <= 7 days old
        g = igt.loc[phrase] if phrase in igt.index else None
        r["ig_posts_per_day"] = float(g["posts_per_day"]) if g is not None and pd.notna(g["posts_per_day"]) else None
        newest = str(g["newest"]) if g is not None and pd.notna(g["newest"]) else ""
        fresh_ig = bool(newest) and newest >= (pd.Timestamp.today() - pd.Timedelta(days=IG_MAX_AGE_DAYS)).strftime("%Y-%m-%d")
        r["check_instagram"] = bool(r["ig_posts_per_day"] is not None and r["ig_posts_per_day"] >= IG_MIN_PER_DAY and fresh_ig)

        checks = ["check_google", "check_pinterest", "check_youtube", "check_tiktok", "check_amazon", "check_retailers",
                  "check_instagram"]
        r["checks_passed"] = int(sum(bool(r[c]) for c in checks))
        # Gates first (user rules), then the channel vote
        r["reject_reason"] = ""
        r["watch_reason"] = ""
        r["steady_demand"] = steady_demand(r)
        if r["short_season"]:
            r["decision"], r["reject_reason"] = "REJECT", "короткий сезон"
        elif not r["stable_growth"]:
            if r["season_soon"]:
                r["decision"] = "WATCH"
                r["watch_reason"] = (f"сезон вот-вот начнётся: год назад в следующие {AHEAD_WEEKS} недель "
                                     f"интерес вырос на {r['season_ahead_pct']:+.0f}%, в этом году не ниже прошлого")
            elif r["steady_demand"] and r["checks_passed"] >= 2:
                # user 22.09.2026: такие вещи — «наблюдать», отдельного решения не нужно
                r["decision"] = "WATCH"
                r["watch_reason"] = "роста к прошлому году нет, но спрос большой и не падает"
            else:
                r["decision"] = "REJECT"
                r["reject_reason"] = ("нет стабильного роста" if phrase in pinterest_series
                                      else "рост не проверить: нет кривой Pinterest")
        elif r["checks_passed"] >= TEST_MIN:
            r["decision"] = "TEST"
        elif r["checks_passed"] >= WATCH_MIN:
            r["decision"] = "WATCH"
        else:
            r["decision"], r["reject_reason"] = "REJECT", "мало подтверждений"
        # User's manual decision overrides the vote, but stays visible as manual (checks are not touched)
        r["auto_decision"], r["manual_reason"] = r["decision"], ""
        if phrase in manual:
            r["decision"], r["manual_reason"] = manual[phrase]
            r["reject_reason"] = "" if r["decision"] != "REJECT" else r["reject_reason"]
        # Audience 28+ (user 23.09.2026: 18-24 is a small audience that can't pay) -> younger items are not ours
        r["aud28_pct"], r["aud28_source"] = audience_28(phrase)
        if (r["decision"] in ("TEST", "WATCH") and phrase not in manual and r["aud28_pct"] is not None
                and r["aud28_pct"] < (AUD28_MIN_GOOGLE if r["aud28_source"] == "Google" else AUD28_MIN_PINTEREST)):
            r["decision"] = "REJECT"
            r["reject_reason"] = f"не наша аудитория: от 28 лет только {r['aud28_pct']:.0f}% интереса ({r['aud28_source']})"
        # Not our season (user 23.09.2026): we sell autumn-winter only -> spring/summer items are rejected, not «позже»
        r["later_reason"] = ""
        if r["decision"] in ("TEST", "WATCH") and not r["in_season"] and phrase not in manual:
            r["decision"] = "REJECT"
            r["reject_reason"] = f"не наш сезон: сезон вещи {r['season_months']}, а мы продаём на {TARGET_LABEL}"
        rows.append(r)

    return sort_candidates(pd.DataFrame(rows))


def sort_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """User rule 22.09.2026: TEST, WATCH, LATER (off-season), REJECT; short-season rejects always last."""
    rank = df["decision"].map({"TEST": 0, "WATCH": 1, "LATER": 2, "REJECT": 3}).fillna(3)
    rank = rank + df["short_season"].fillna(False).astype(bool).astype(int)
    return (df.assign(_rank=rank)
              .sort_values(["_rank", "checks_passed", "pin_yoy_pct"], ascending=[True, False, False], na_position="last")
              .drop(columns="_rank").reset_index(drop=True))
