import time
import pandas as pd
from config.settings import EXPORT_DIR
from src.collectors.instagram_collector import InstagramCollector
from src.processors.instagram_normalize import normalize_instagram_results
from src.processors.instagram_scoring import compute_instagram_score
from src.storage.files import save_csv, timestamp

URLS_FILE = "config/instagram_urls.csv"


def main():
    collector = InstagramCollector()
    urls_df = pd.read_csv(URLS_FILE)

    ts = timestamp()
    summary_rows = []
    all_posts = []

    keywords = urls_df["keyword"].unique()
    for i, keyword in enumerate(keywords):
        urls = urls_df[urls_df["keyword"] == keyword]["url"].tolist()
        print(f"[{i + 1}/{len(keywords)}] {keyword} ({len(urls)} urls)")

        if i > 0:
            time.sleep(10)

        try:
            rows = collector.fetch_urls(urls)
        except Exception as e:
            print(f"  failed: {e}")
            summary_rows.append({
                "keyword": keyword, "instagram_score": None, "post_count": 0,
                "unique_authors": 0, "top_hashtags": "",
            })
            continue

        df = normalize_instagram_results(keyword, rows)
        score, top_tags, unique_authors = compute_instagram_score(df)
        print(f"  found {len(df)} posts, {unique_authors} unique authors, score={score}")

        summary_rows.append({
            "keyword": keyword,
            "instagram_score": score,
            "post_count": len(df),
            "unique_authors": unique_authors,
            "top_hashtags": top_tags,
        })

        if not df.empty:
            all_posts.append(df)

    summary_df = pd.DataFrame(summary_rows).sort_values("instagram_score", ascending=False)
    save_csv(summary_df, f"{EXPORT_DIR}/instagram_summary_{ts}.csv")

    if all_posts:
        posts_df = pd.concat(all_posts, ignore_index=True)
        save_csv(posts_df, f"{EXPORT_DIR}/instagram_posts_{ts}.csv")


if __name__ == "__main__":
    main()
