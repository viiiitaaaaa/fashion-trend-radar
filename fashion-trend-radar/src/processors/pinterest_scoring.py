import math
from datetime import datetime, timezone


def compute_pinterest_score(df):
    if df.empty:
        return 0, ""

    post_count = len(df)
    now = datetime.now(timezone.utc)
    recent_count = 0

    for raw_date in df["date_posted"].dropna():
        try:
            dt = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
            if (now - dt).days <= 180:
                recent_count += 1
        except ValueError:
            continue

    recency_ratio = recent_count / post_count if post_count else 0

    likes = df["likes"].dropna().tolist()
    # median is more robust than mean/sum against a single viral outlier pin
    sorted_likes = sorted(likes)
    n = len(sorted_likes)
    median_likes = (
        sorted_likes[n // 2] if n % 2 else (sorted_likes[n // 2 - 1] + sorted_likes[n // 2]) / 2
    ) if n else 0
    # log-compressed so a viral outlier doesn't drown out consistently-liked keywords
    likes_component = math.log1p(median_likes) * 10

    tag_counter = {}
    for tags in df["hashtags"].dropna():
        for tag in tags.split(","):
            tag = tag.strip()
            if tag:
                tag_counter[tag] = tag_counter.get(tag, 0) + 1

    top_tags = sorted(tag_counter.items(), key=lambda x: -x[1])[:5]
    top_tags_str = "; ".join(f"{t} ({c})" for t, c in top_tags)

    score = round(
        post_count * 0.3 + recency_ratio * 100 * 0.2 + likes_component * 0.5, 2
    )
    return score, top_tags_str
