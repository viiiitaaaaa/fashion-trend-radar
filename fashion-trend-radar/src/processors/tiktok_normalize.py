import pandas as pd


def _num(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_tiktok_results(keyword, rows):
    records = []
    for item in rows:
        if not isinstance(item, dict) or "error" in item:
            continue
        plays = _num(item.get("play_count"))
        likes = _num(item.get("digg_count"))
        comments = _num(item.get("comment_count"))
        shares = _num(item.get("share_count"))
        saves = _num(item.get("collect_count"))
        engagement_rate = round((likes + comments + shares + saves) / plays, 4) if plays else None
        records.append({
            "keyword": keyword,
            "url": item.get("url"),
            "post_id": item.get("post_id"),
            "description": item.get("description"),
            "create_time": item.get("create_time"),
            "author": item.get("profile_username"),
            "author_followers": item.get("profile_followers"),
            "plays": plays,
            "likes": likes,
            "comments_num": comments,
            "shares": shares,
            "saves": saves,
            "engagement_rate": engagement_rate,
            "duration_sec": item.get("video_duration"),
            "hashtags": ",".join(item.get("hashtags") or []),
            "preview_image": item.get("preview_image"),
            "video_url": item.get("video_url"),
        })
    return pd.DataFrame(records)
