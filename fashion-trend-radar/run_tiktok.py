import time
import pandas as pd
from config.settings import KEYWORDS_FILE, EXPORT_DIR
from src.collectors.tiktok_collector import TikTokCollector
from src.processors.tiktok_normalize import normalize_tiktok_results
from src.processors.tiktok_scoring import compute_tiktok_score
from src.storage.files import save_csv, timestamp


def main():
    collector = TikTokCollector()
    keywords_df = pd.read_csv(KEYWORDS_FILE)

    ts = timestamp()
    summary_rows = []
    all_videos = []

    for i, (_, row) in enumerate(keywords_df.iterrows()):
        keyword = row["keyword"]
        print(f"[{i + 1}/{len(keywords_df)}] {keyword}")

        if i > 0:
            time.sleep(15)

        try:
            rows = collector.fetch_keyword_data(keyword=keyword, limit=20)
        except Exception as e:
            print(f"  failed: {e}")
            summary_rows.append({
                "keyword": keyword, "category": row.get("category"), "style": row.get("style"),
                "tiktok_score": None, "post_count": 0, "unique_authors": 0, "top_hashtags": "",
            })
            continue

        df = normalize_tiktok_results(keyword, rows)
        score, top_tags, unique_authors = compute_tiktok_score(df)
        print(f"  found {len(df)} videos, {unique_authors} unique authors, score={score}")

        summary_rows.append({
            "keyword": keyword,
            "category": row.get("category"),
            "style": row.get("style"),
            "tiktok_score": score,
            "post_count": len(df),
            "unique_authors": unique_authors,
            "top_hashtags": top_tags,
        })

        if not df.empty:
            all_videos.append(df)

    summary_df = pd.DataFrame(summary_rows).sort_values("tiktok_score", ascending=False)
    save_csv(summary_df, f"{EXPORT_DIR}/tiktok_summary_{ts}.csv")

    if all_videos:
        videos_df = pd.concat(all_videos, ignore_index=True)
        save_csv(videos_df, f"{EXPORT_DIR}/tiktok_videos_{ts}.csv")


if __name__ == "__main__":
    main()
