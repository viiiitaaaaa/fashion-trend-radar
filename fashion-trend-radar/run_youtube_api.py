"""
YouTube Data API v3 for chosen candidates (official API, key in .env as
YOUTUBE_API_KEY). Per candidate:
  - videos published in the last 90 days vs the same 90 days a year earlier (US)
  - views / likes / comments of the recent videos
  - purchase intent: share of comments asking where to buy / link / brand / price
Quota: ~210 units per candidate (2 searches x 100 + a few 1-unit calls) of 10,000/day.
Output: data/processed/youtube_api.csv, raw JSON in data/raw/youtube_api/
Usage: .venv/Scripts/python.exe run_youtube_api.py "roll neck sweater" "hoco dress" ...
"""
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

API = "https://www.googleapis.com/youtube/v3"
DAYS = 90
TOP_FOR_COMMENTS = 10
RAW = Path("data/raw/youtube_api")
RAW.mkdir(parents=True, exist_ok=True)

INTENT = re.compile(
    r"where (can i|did you|do i|to|is (it|this|that|the)).{0,20}(get|buy|find|from)"
    r"|link\b|links\b|what brand|which brand|brand\?|where.{0,15}from\?"
    r"|how much|price\?|need (this|it|that)|want (this|it|that)|sizing|what size",
    re.I,
)
# regionCode=US doesn't exclude South-Asian marketplace hauls (Myntra/Flipkart) --
# drop channels whose declared country is outside the target market
EXCLUDE_COUNTRIES = {"IN", "PK", "BD", "NP", "LK"}


def api_key():
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("YOUTUBE_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("Нет YOUTUBE_API_KEY в .env")


KEY = api_key()


def get(path, **params):
    r = requests.get(f"{API}/{path}", params={**params, "key": KEY}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"{path}: HTTP {r.status_code} {r.text[:300]}")
    time.sleep(0.5)
    return r.json()


def search(q, after, before):
    """One search page (100 units). totalResults is YouTube's own estimate."""
    j = get("search", part="id", q=q, type="video", regionCode="US", relevanceLanguage="en",
            publishedAfter=after.isoformat().replace("+00:00", "Z"),
            publishedBefore=before.isoformat().replace("+00:00", "Z"),
            order="viewCount", maxResults=50)
    ids = [it["id"]["videoId"] for it in j.get("items", [])]
    return ids, j.get("pageInfo", {}).get("totalResults", 0)


def stats(ids):
    if not ids:
        return []
    j = get("videos", part="statistics,snippet", id=",".join(ids[:50]))
    out = []
    for it in j.get("items", []):
        s = it.get("statistics", {})
        out.append({"id": it["id"], "title": it["snippet"]["title"],
                    "channel": it["snippet"]["channelTitle"], "channel_id": it["snippet"]["channelId"],
                    "published": it["snippet"]["publishedAt"][:10],
                    "views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                    "comments": int(s.get("commentCount", 0))})
    return keep_target_market(out)


def keep_target_market(vids):
    """1 unit: channel countries; channels without a declared country are kept."""
    ch_ids = list({v["channel_id"] for v in vids})[:50]
    if not ch_ids:
        return vids
    j = get("channels", part="snippet", id=",".join(ch_ids))
    country = {it["id"]: it["snippet"].get("country") for it in j.get("items", [])}
    for v in vids:
        v["channel_country"] = country.get(v["channel_id"])
    return [v for v in vids if v.get("channel_country") not in EXCLUDE_COUNTRIES]


def comments(video_id):
    try:
        j = get("commentThreads", part="snippet", videoId=video_id, maxResults=100,
                order="relevance", textFormat="plainText")
    except RuntimeError:  # comments disabled
        return []
    return [it["snippet"]["topLevelComment"]["snippet"]["textDisplay"] for it in j.get("items", [])]


def collect(cand):
    now = datetime.now(timezone.utc)
    ids_now, total_now = search(cand, now - timedelta(days=DAYS), now)
    ids_prev, total_prev = search(cand, now - timedelta(days=365 + DAYS), now - timedelta(days=365))
    vids = stats(ids_now)
    prev_vids = stats(ids_prev)
    top = sorted(vids, key=lambda v: v["views"], reverse=True)[:TOP_FOR_COMMENTS]
    all_comments, intent_hits = [], []
    for v in top:
        cs = comments(v["id"])
        all_comments += cs
        intent_hits += [c for c in cs if INTENT.search(c)]
    (RAW / f"{cand.replace(' ', '_')}_{now.date()}.json").write_text(json.dumps(
        {"videos": vids, "prev_videos": prev_vids, "comments": all_comments, "intent": intent_hits},
        ensure_ascii=False), encoding="utf-8")

    views_now = sum(v["views"] for v in vids)
    views_prev = sum(v["views"] for v in prev_vids)
    pct = lambda a, b: round((a - b) / b * 100, 1) if b else None
    return {
        "candidate": cand,
        "yt_videos_90d": len(vids), "yt_videos_90d_last_year": len(prev_vids),
        "yt_total_est_90d": total_now, "yt_total_est_last_year": total_prev,
        "yt_views_90d": views_now, "yt_views_last_year": views_prev,
        "yt_views_yoy_pct": pct(views_now, views_prev),
        "yt_channels_90d": len({v["channel"] for v in vids}),
        "yt_comments_read": len(all_comments),
        "yt_intent_comments": len(intent_hits),
        "yt_intent_pct": round(len(intent_hits) / len(all_comments) * 100, 1) if all_comments else None,
        "yt_intent_examples": " | ".join(c.replace("\n", " ")[:90] for c in intent_hits[:3]),
        "yt_top_video": (f"{top[0]['title'][:70]} ({top[0]['views']:,} просм.)" if top else ""),
    }


def main():
    cands = sys.argv[1:] or ["roll neck sweater", "hoco dress", "lace trim top"]
    rows = []
    for c in cands:
        try:
            r = collect(c)
            rows.append(r)
            print(f"{c}: видео за 90 дн {r['yt_videos_90d']} (год назад {r['yt_videos_90d_last_year']}), "
                  f"просмотры {r['yt_views_90d']:,} vs {r['yt_views_last_year']:,} ({r['yt_views_yoy_pct']}%), "
                  f"каналов {r['yt_channels_90d']}, комментариев {r['yt_comments_read']}, "
                  f"«где купить» {r['yt_intent_comments']} ({r['yt_intent_pct']}%)")
        except RuntimeError as e:
            print(f"{c}: ОШИБКА {e}")
    if not rows:
        return
    out = Path("data/processed/youtube_api.csv")
    new = pd.DataFrame(rows)
    if out.exists():  # keep other candidates from earlier runs
        old = pd.read_csv(out)
        new = pd.concat([old[~old["candidate"].isin(new["candidate"])], new], ignore_index=True)
    new.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"Сохранено: {out}")


if __name__ == "__main__":
    main()
