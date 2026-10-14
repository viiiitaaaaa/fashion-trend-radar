import pandas as pd


def _num(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_instagram_results(keyword, rows):
    records = []
    for item in rows:
        if not isinstance(item, dict) or item.get("error"):
            continue
        records.append({
            "keyword": keyword,
            "url": item.get("url"),
            "post_id": item.get("post_id"),
            "description": item.get("description"),
            "date_posted": item.get("date_posted"),
            "author": item.get("user_posted"),
            "author_followers": _num(item.get("followers")),
            "likes": _num(item.get("likes")),
            "comments_num": _num(item.get("num_comments")),
            "hashtags": ",".join(item.get("hashtags") or []),
            "is_verified": item.get("is_verified"),
            "thumbnail": item.get("thumbnail"),
        })
    return pd.DataFrame(records)
