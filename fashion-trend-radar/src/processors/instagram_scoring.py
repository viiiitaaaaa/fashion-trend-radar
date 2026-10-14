import math
from datetime import datetime, timezone


def compute_instagram_score(df):
    """No view/play count is available for Reels via this dataset (Instagram
    doesn't expose it for posts you don't own), so this scores on likes,
    comments and unique-author spread rather than an engagement RATE."""
    if df.empty:
        return 0, "", 0

    post_count = len(df)
    unique_authors = df["author"].dropna().nunique()

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

    likes = sorted(df["likes"].dropna().tolist())
    n = len(likes)
    median_likes = (likes[n // 2] if n % 2 else (likes[n // 2 - 1] + likes[n // 2]) / 2) if n else 0
    likes_component = math.log1p(median_likes)

    comments = sorted(df["comments_num"].dropna().tolist())
    m = len(comments)
    median_comments = (comments[m // 2] if m % 2 else (comments[m // 2 - 1] + comments[m // 2]) / 2) if m else 0
    comments_component = math.log1p(median_comments)

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
        + likes_component * 5
        + comments_component * 5,
        2,
    )
    return score, top_tags_str, unique_authors
