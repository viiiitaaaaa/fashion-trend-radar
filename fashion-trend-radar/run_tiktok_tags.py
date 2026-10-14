"""
TikTok by OUR candidates' hashtags, US market, via treg.to (provider TikHub, $0.001 per successful call).
Per candidate: hashtag detail (total videos / views, worldwide) + up to 30 US videos under the tag.
Runs only by hand.

    .venv/Scripts/python.exe run_tiktok_tags.py                  # all candidates
    .venv/Scripts/python.exe run_tiktok_tags.py "bandana cardigan"

Output: data/processed/tiktok_tags.csv        (one row per candidate)
        data/processed/tiktok_tag_videos.csv  (videos with links)
"""
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
from dotenv import dotenv_values

env = dotenv_values(".env")
H = {"X-Treg-Token": env["TREG_TOKEN"], "X-Treg-Org": env.get("TREG_ORG", "vi")}
RAW = Path("data/raw/treg")
RAW.mkdir(parents=True, exist_ok=True)
REGION = "US"
TAGS = {   # candidate -> hashtag people actually use (default: phrase without spaces)
    "womens fall jacket": "falljacket",
    "flannel shirt women": "flannelshirt",
}
spent = 0.0


def call(endpoint: str, **params):
    global spent
    r = requests.get(f"https://treg.to/call/{endpoint}", headers=H, params=params, timeout=60)
    spent += int(r.headers.get("X-Treg-Cost-Micro") or 0) / 1e6
    try:
        data = r.json()
    except ValueError:
        data = {"raw_text": r.text[:2000]}
    tag = "_".join(str(v) for v in params.values())[:60]
    (RAW / f"{datetime.now():%Y%m%d_%H%M%S}_{endpoint}_{tag}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if r.status_code != 200:
        raise RuntimeError(f"{endpoint}: HTTP {r.status_code} {str(data)[:200]}")
    return data


def walk(obj, pred):
    if isinstance(obj, dict):
        if pred(obj):
            yield obj
            return
        for v in obj.values():
            yield from walk(v, pred)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v, pred)


def hashtag_detail(tag):
    d = call("tikhub.tiktok.hashtag.detail", tag_name=tag)
    info = (d.get("data") or {}).get("challengeInfo") or {}
    ch = info.get("challenge") or {}
    st = info.get("statsV2") or info.get("stats") or ch.get("stats") or {}   # statsV2 has the real videoCount
    num = lambda x: int(float(x)) if x not in (None, "") else None
    cid = ch.get("id")
    return str(cid) if cid else None, num(st.get("videoCount")), num(st.get("viewCount"))


PAGES = 3   # ~30 videos a page; 3 pages give enough dates for a weekly chart


def us_videos(cid, n=30):
    items, cursor = [], 0
    for _ in range(PAGES):
        d = call("tikhub.x.tiktok-app-v3-fetch-hashtag-video-list", ch_id=cid, count=n, region=REGION, cursor=cursor)
        items += list(walk(d, lambda o: ("aweme_id" in o or "id" in o) and isinstance(o.get("author"), dict)))
        data = d.get("data") or {}
        if not data.get("has_more") or not data.get("cursor"):
            break
        cursor = data["cursor"]
    out = []
    for v in items:
        a = v["author"]
        st = v.get("statistics") or v.get("stats") or {}
        vid = str(v.get("aweme_id") or v.get("id"))
        user = a.get("unique_id") or a.get("uniqueId") or ""
        ts = v.get("create_time") or v.get("createTime")
        out.append({
            "link": f"https://www.tiktok.com/@{user}/video/{vid}",
            "author": user,
            "region": v.get("region") or a.get("region") or "",
            "created": datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d") if ts else "",
            "views": st.get("play_count") or st.get("playCount"),
            "likes": st.get("digg_count") or st.get("diggCount"),
            "shares": st.get("share_count") or st.get("shareCount"),
            "desc": (v.get("desc") or "").replace("\n", " ")[:150],
        })
    return list({v["link"]: v for v in out}.values())   # pages can repeat a video


def save_merged(df_new, path, key="candidate"):
    """Partial runs (a few candidates) must not wipe the others: replace only the rows of the candidates just collected."""
    path = Path(path)
    if df_new.empty and path.exists():
        return   # nothing collected (provider error) — keep what is there
    if path.exists() and not df_new.empty and key in df_new:
        old = pd.read_csv(path)
        if key in old:
            df_new = pd.concat([old[~old[key].isin(df_new[key].unique())], df_new], ignore_index=True)
    df_new.to_csv(path, index=False, encoding="utf-8-sig")


def main():
    cands = sys.argv[1:] or pd.read_csv("config/candidates.csv")["candidate"].tolist()
    summary, videos = [], []
    since = (date.today() - timedelta(days=30)).isoformat()
    for c in cands:
        tag = TAGS.get(c, c.replace(" ", "").lower())
        try:
            cid, total_videos, total_views = hashtag_detail(tag)
            vids = us_videos(cid) if cid else []
        except RuntimeError as e:
            print(f"  {c}: {e}")
            cid, total_videos, total_views, vids = None, None, None, []
        for v in vids:
            v.update(candidate=c, hashtag=tag)
        videos += vids
        us = [v for v in vids if v["region"] in ("", REGION)]
        fresh = [v for v in us if v["created"] >= since]
        summary.append({
            "candidate": c, "hashtag": tag, "challenge_id": cid,
            "total_videos": total_videos, "total_views": total_views,
            "us_videos_sampled": len(us), "us_fresh_30d": len(fresh),
            "us_fresh_views": int(sum(v["views"] or 0 for v in fresh)),
            "top_video": max(us, key=lambda v: v["views"] or 0)["link"] if us else "",
            "date": str(date.today()),
        })
        s = summary[-1]
        print(f"  #{tag:<22} всего видео {s['total_videos']!s:>9}, просмотров {s['total_views']!s:>13}; "
              f"US: {s['us_videos_sampled']:>2} видео, свежих за 30 дн {s['us_fresh_30d']:>2}")
    out = Path("data/processed")
    save_merged(pd.DataFrame(summary), out / "tiktok_tags.csv")
    save_merged(pd.DataFrame(videos), out / "tiktok_tag_videos.csv")
    print(f"Потрачено: ${spent:.4f}. Сохранено: data/processed/tiktok_tags.csv, tiktok_tag_videos.csv")


if __name__ == "__main__":
    main()
