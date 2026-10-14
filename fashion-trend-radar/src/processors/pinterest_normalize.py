import pandas as pd


def normalize_pinterest_results(keyword, rows):
    records = []
    for item in rows:
        if not isinstance(item, dict) or "error" in item:
            continue
        records.append({
            "keyword": keyword,
            "pin_title": item.get("title"),
            "likes": item.get("likes"),
            "comments_num": item.get("comments_num"),
            "date_posted": item.get("date_posted"),
            "categories": ",".join(item.get("categories") or []),
            "hashtags": ",".join(item.get("hashtags") or []),
            "url": item.get("url"),
        })
    return pd.DataFrame(records)
