import time
import pandas as pd
from config.settings import KEYWORDS_FILE, RAW_DIR, EXPORT_DIR
from src.collectors.google_trends_collector import GoogleTrendsCollector
from src.storage.files import save_json, save_csv, timestamp
from src.processors.normalize import (
    normalize_brightdata_timeseries,
    normalize_brightdata_geo_map,
    normalize_related_topics_and_queries,
)
from src.processors.scoring import compute_keyword_score


def main():
    collector = GoogleTrendsCollector()
    keywords_df = pd.read_csv(KEYWORDS_FILE)

    ts = timestamp()
    all_frames = []
    geo_frames = []
    topic_frames = []
    query_frames = []
    summary_rows = []

    for i, (_, row) in enumerate(keywords_df.iterrows()):
        keyword = row["keyword"]
        category = row.get("category") if hasattr(row, "get") else None

        if i > 0:
            time.sleep(45)

        raw = collector.fetch_keyword_data(keyword=keyword, category=category)
        save_json(raw, f"{RAW_DIR}/{keyword.replace(' ', '_')}_{ts}.json")

        ts_df = normalize_brightdata_timeseries(keyword, raw)
        geo_df = normalize_brightdata_geo_map(keyword, raw)
        topics_df, queries_df = normalize_related_topics_and_queries(keyword, raw)

        if not ts_df.empty:
            all_frames.append(ts_df)
            score = compute_keyword_score(ts_df)
            summary_rows.append({
                "keyword": keyword,
                "category": row.get("category"),
                "style": row.get("style"),
                "priority": row.get("priority"),
                "score": score,
                "latest_value": ts_df["value"].dropna().iloc[-1] if not ts_df["value"].dropna().empty else None,
                "avg_value": round(ts_df["value"].dropna().mean(), 2) if not ts_df["value"].dropna().empty else None
            })

        if not geo_df.empty:
            geo_frames.append(geo_df)

        if not topics_df.empty:
            topic_frames.append(topics_df)
        if not queries_df.empty:
            query_frames.append(queries_df)

    if all_frames:
        full_df = pd.concat(all_frames, ignore_index=True)
        save_csv(full_df, f"{EXPORT_DIR}/trends_timeseries_{ts}.csv")

    if geo_frames:
        geo_full_df = pd.concat(geo_frames, ignore_index=True)
        save_csv(geo_full_df, f"{EXPORT_DIR}/trends_geo_{ts}.csv")

    if topic_frames:
        save_csv(pd.concat(topic_frames, ignore_index=True), f"{EXPORT_DIR}/trends_related_topics_{ts}.csv")

    if query_frames:
        save_csv(pd.concat(query_frames, ignore_index=True), f"{EXPORT_DIR}/trends_related_queries_{ts}.csv")

    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values("score", ascending=False)
    save_csv(summary_df, f"{EXPORT_DIR}/trends_summary_{ts}.csv")


if __name__ == "__main__":
    main()
