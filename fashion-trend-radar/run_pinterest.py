import time
import pandas as pd
from config.settings import KEYWORDS_FILE, EXPORT_DIR
from src.collectors.pinterest_collector import PinterestCollector
from src.processors.pinterest_normalize import normalize_pinterest_results
from src.processors.pinterest_scoring import compute_pinterest_score
from src.storage.files import save_csv, timestamp


def main():
    collector = PinterestCollector()
    keywords_df = pd.read_csv(KEYWORDS_FILE)

    ts = timestamp()
    summary_rows = []
    all_pins = []

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
                "pinterest_score": None, "post_count": 0, "top_related_hashtags": "",
            })
            continue

        df = normalize_pinterest_results(keyword, rows)
        score, top_tags = compute_pinterest_score(df)

        summary_rows.append({
            "keyword": keyword,
            "category": row.get("category"),
            "style": row.get("style"),
            "pinterest_score": score,
            "post_count": len(df),
            "top_related_hashtags": top_tags,
        })

        if not df.empty:
            all_pins.append(df)

    summary_df = pd.DataFrame(summary_rows).sort_values("pinterest_score", ascending=False)
    save_csv(summary_df, f"{EXPORT_DIR}/pinterest_summary_{ts}.csv")

    if all_pins:
        pins_df = pd.concat(all_pins, ignore_index=True)
        save_csv(pins_df, f"{EXPORT_DIR}/pinterest_pins_{ts}.csv")


if __name__ == "__main__":
    main()
