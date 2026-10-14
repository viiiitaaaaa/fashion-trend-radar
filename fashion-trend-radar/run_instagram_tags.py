"""
Instagram by OUR candidates' hashtags via treg.to (provider TikHub, $0.002 per call): the most recent posts.
Instagram has no country filter -> worldwide. From the newest ~36 posts: how many posts a day the tag gets,
likes, and links to the most liked fresh posts. Runs only by hand.

    .venv/Scripts/python.exe run_instagram_tags.py                  # all candidates
    .venv/Scripts/python.exe run_instagram_tags.py "bandana cardigan"

Output: data/processed/instagram_tags.csv, data/processed/instagram_tag_posts.csv
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
ENDPOINT = "tikhub.x.instagram-v2-fetch-hashtag-posts"
PAGES = 3
TAGS = {"womens fall jacket": "falljacket", "flannel shirt women": "flannelshirt"}   # same as run_tiktok_tags.py
spent = 0.0


def call(**params):
    global spent
    r = requests.get(f"https://treg.to/call/{ENDPOINT}", headers=H, params=params, timeout=90)
    spent += int(r.headers.get("X-Treg-Cost-Micro") or 0) / 1e6
    d = r.json()
    (RAW / f"{datetime.now():%Y%m%d_%H%M%S}_instagram_{params['keyword']}.json").write_text(
        json.dumps(d, ensure_ascii=False), encoding="utf-8")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} {str(d)[:200]}")
    return d


def recent_posts(tag):
    posts, token = [], None
    for _ in range(PAGES):
        params = {"keyword": tag, "feed_type": "recent"}
        if token:
            params["pagination_token"] = token
        d = (call(**params).get("data") or {})
        for x in ((d.get("data") or {}).get("items") or []):
            if not x.get("taken_at") or not x.get("code"):
                continue
            cap = (x.get("caption") or {}).get("text") or ""
            posts.append({
                "link": f"https://www.instagram.com/p/{x['code']}/",
                "taken_at": datetime.fromtimestamp(x["taken_at"]).strftime("%Y-%m-%d %H:%M"),
                "likes": x.get("like_count"), "comments": x.get("comment_count"),
                "user": ((x.get("user") or {}).get("username")) or "",
                "caption": cap.replace("\n", " ")[:150],
            })
        token = d.get("pagination_token")
        if not token:
            break
    return list({p["link"]: p for p in posts}.values())


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


def top_posts(tag):
    """Routed treg endpoint (best of 4 providers, capped at $0.003/call so the $1 provider is never used)."""
    global spent
    h = dict(H, **{"Content-Type": "application/json", "X-Treg-Route-Max-Cost": "0.003"})
    r = requests.post("https://treg.to/call/treg.instagram.hashtag.posts", headers=h, json={"hashtag": tag}, timeout=120)
    spent += int(r.headers.get("X-Treg-Cost-Micro") or 0) / 1e6
    d = r.json()
    (RAW / f"{datetime.now():%Y%m%d_%H%M%S}_instagram-top_{tag}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    out = []
    for x in ((d.get("output") or {}).get("posts") or []):
        if not x.get("taken_at") or not x.get("shortcode"):
            continue
        out.append({"link": f"https://www.instagram.com/p/{x['shortcode']}/",
                    "taken_at": pd.Timestamp(x["taken_at"]).strftime("%Y-%m-%d %H:%M"),
                    "likes": x.get("like_count"), "comments": x.get("comment_count"),
                    "user": (x.get("owner") or {}).get("username", "") if isinstance(x.get("owner"), dict) else "",
                    "caption": (x.get("caption") or "").replace("\n", " ")[:150]})
    return out


def main():
    cands = sys.argv[1:] or pd.read_csv("config/candidates.csv")["candidate"].tolist()
    summary, allposts = [], []
    for c in cands:
        tag = TAGS.get(c, c.replace(" ", "").lower())
        sample = "recent"
        try:
            posts = recent_posts(tag)
        except (RuntimeError, ValueError) as e:
            print(f"  {c}: {str(e)[:80]}")
            posts = []
        if not posts:   # 23.09.2026: the TikHub «recent» route broke -> treg's routed endpoint (TOP posts, not recent)
            posts, sample = top_posts(tag), "top"
            print(f"  #{tag}: запасной вход — лучшие посты ({len(posts)})")
        for p in posts:
            p.update(candidate=c, hashtag=tag)
        allposts += posts
        times = sorted(datetime.strptime(p["taken_at"], "%Y-%m-%d %H:%M") for p in posts)
        span = (times[-1] - times[0]).total_seconds() / 86400 if len(times) > 1 else None
        per_day = round(len(times) / max(span, 1 / 24), 1) if span is not None and sample == "recent" else None
        likes = [p["likes"] for p in posts if p["likes"] is not None]
        summary.append({
            "candidate": c, "hashtag": tag, "posts_sampled": len(posts),
            "newest": times[-1].strftime("%Y-%m-%d") if times else "",
            "oldest": times[0].strftime("%Y-%m-%d") if times else "",
            "posts_per_day": per_day,
            "likes_median": int(pd.Series(likes).median()) if likes else None, "sample": sample,
            "date": str(date.today()),
        })
        s = summary[-1]
        print(f"  #{tag:<22} постов {s['posts_sampled']:>3}, с {s['oldest']} по {s['newest']}, в день ≈ {s['posts_per_day']}")
    out = Path("data/processed")
    save_merged(pd.DataFrame(summary), out / "instagram_tags.csv")
    save_merged(pd.DataFrame(allposts), out / "instagram_tag_posts.csv")
    print(f"Потрачено: ${spent:.4f}. Сохранено: data/processed/instagram_tags.csv, instagram_tag_posts.csv")


if __name__ == "__main__":
    main()
