"""
Today's trending TikTok videos (explore feed) + daily trending search words, via treg.to (provider TikHub).
Cost: $0.001 per successful call. Runs only by hand.
Key: TREG_TOKEN / TREG_ORG in .env.  Output: data/raw/treg/ (raw) + data/processed/tiktok_trending_<date>.csv
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import dotenv_values

env = dotenv_values(".env")
H = {"X-Treg-Token": env["TREG_TOKEN"], "X-Treg-Org": env.get("TREG_ORG", "vi")}
RAW = Path("data/raw/treg")
RAW.mkdir(parents=True, exist_ok=True)


def call(endpoint: str, **params):
    r = requests.get(f"https://treg.to/call/{endpoint}", headers=H, params=params, timeout=60)
    cost = int(r.headers.get("X-Treg-Cost-Micro") or 0) / 1e6
    try:
        data = r.json()
    except ValueError:
        data = {"raw_text": r.text[:2000]}
    (RAW / f"{datetime.now():%Y%m%d_%H%M%S}_{endpoint}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{endpoint}: HTTP {r.status_code}, стоимость ${cost:.4f}")
    r.raise_for_status()
    return data


def find_videos(obj):
    """TikHub answers differ by endpoint: walk the JSON and take every dict that looks like a video item."""
    out = []
    if isinstance(obj, dict):
        vid = obj.get("id") or obj.get("aweme_id")
        author = obj.get("author")
        if vid and isinstance(author, dict) and (obj.get("desc") is not None or obj.get("stats") or obj.get("statistics")):
            out.append(obj)
        else:
            for v in obj.values():
                out += find_videos(v)
    elif isinstance(obj, list):
        for v in obj:
            out += find_videos(v)
    return out


def main():
    # the explore feed returns ~3 videos per call whatever `count` says -> ask several pages
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    videos = []
    for _ in range(pages):
        videos += find_videos(call("tikhub.x.tiktok-web-fetch-explore-post", count=16))
    rows = []
    for v in videos:
        a, st = v.get("author") or {}, v.get("stats") or v.get("statistics") or {}
        user = a.get("uniqueId") or a.get("unique_id") or ""
        vid = str(v.get("id") or v.get("aweme_id"))
        desc = v.get("desc") or " ".join(c.get("desc", "") for c in (v.get("contents") or []))
        rows.append({
            "link": f"https://www.tiktok.com/@{user}/video/{vid}",
            "author": user,
            "desc": desc.replace("\n", " ")[:160],
            "views": st.get("playCount") or st.get("play_count"),
            "likes": st.get("diggCount") or st.get("digg_count"),
            "comments": st.get("commentCount") or st.get("comment_count"),
            "shares": st.get("shareCount") or st.get("share_count"),
            "created": datetime.fromtimestamp(int(v["createTime"])).strftime("%Y-%m-%d") if v.get("createTime") else "",
            "hashtags": " ".join("#" + t.get("hashtagName", "") for t in (v.get("textExtra") or []) if t.get("hashtagName")),
        })
    df = pd.DataFrame(rows).drop_duplicates("link")
    if not df.empty:
        df = df.sort_values("views", ascending=False, na_position="last")
    out = Path(f"data/processed/tiktok_trending_{date.today()}.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"Видео: {len(df)} -> {out}")

    if "--no-searches" in sys.argv:
        return
    words = call("tikhub.x.tiktok-web-fetch-trending-searchwords")
    (Path("data/processed") / f"tiktok_trending_searches_{date.today()}.json").write_text(
        json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
