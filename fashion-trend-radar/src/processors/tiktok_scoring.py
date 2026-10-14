import math
from datetime import datetime, timezone


def compute_tiktok_score(df):
    """Weights independent creators and engagement RATE over raw plays --
    per the "не путай охваты и спрос" rule: a single high-play, low-engagement
    video is a media fluke, not a repeatable pattern. Recency window is 90
    days (TikTok trends decay faster than Pinterest's 180-day window)."""
    if df.empty:
        return 0, "", 0

    post_count = len(df)
    unique_authors = df["author"].dropna().nunique()

    now = datetime.now(timezone.utc)
    recent_count = 0
    for raw_date in df["create_time"].dropna():
        try:
            dt = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
            if (now - dt).days <= 90:
                recent_count += 1
        except ValueError:
            continue
    recency_ratio = recent_count / post_count if post_count else 0

    plays = sorted(df["plays"].dropna().tolist())
    n = len(plays)
    median_plays = (plays[n // 2] if n % 2 else (plays[n // 2 - 1] + plays[n // 2]) / 2) if n else 0
    plays_component = math.log1p(median_plays)

    rates = sorted(df["engagement_rate"].dropna().tolist())
    m = len(rates)
    median_rate = (rates[m // 2] if m % 2 else (rates[m // 2 - 1] + rates[m // 2]) / 2) if m else 0

    tag_counter = {}
    for tags in df["hashtags"].dropna():
        for tag in tags.split(","):
            tag = tag.strip()
            if tag:
                tag_counter[tag] = tag_counter.get(tag, 0) + 1
    top_tags = sorted(tag_counter.items(), key=lambda x: -x[1])[:5]
    top_tags_str = "; ".join(f"{t} ({c})" for t, c in top_tags)

    score = round(
        unique_authors * 3
        + recency_ratio * 100 * 0.15
        + plays_component * 3
        + median_rate * 1000 * 0.4,
        2,
    )
    return score, top_tags_str, unique_authors
