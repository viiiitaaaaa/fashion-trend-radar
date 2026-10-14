import time
import pandas as pd
from config.settings import KEYWORDS_FILE, EXPORT_DIR
from src.collectors.aliexpress_collector import AliExpressCollector
from src.processors.aliexpress_filter import filter_products
from src.storage.files import save_csv, timestamp


def main():
    collector = AliExpressCollector()
    keywords_df = pd.read_csv(KEYWORDS_FILE)

    ts = timestamp()
    all_rows = []

    sourcing_rows = keywords_df[keywords_df.get("gender", "women") == "women"]

    for i, (_, row) in enumerate(sourcing_rows.iterrows()):
        keyword = row["keyword"]
        search_text = f"women's {keyword}"
        print(f"[{i + 1}/{len(sourcing_rows)}] {keyword}  (search: {search_text!r})")

        if i > 0:
            time.sleep(5)

        try:
            rows = collector.fetch_keyword_data(keyword=keyword, limit=40, search_text=search_text, pages=3)
        except Exception as e:
            print(f"  failed: {e}")
            continue

        kept = filter_products(rows, min_rating=4.0, min_price=15.0, max_price=60.0)
        print(f"  found {len(rows)} products, {len(kept)} passed rating>4 / $15<=price<=$60 / has sales+reviews")
        all_rows.extend(kept)

    if all_rows:
        df = pd.DataFrame(all_rows)
        save_csv(df, f"{EXPORT_DIR}/aliexpress_products_{ts}.csv")
        print(f"Saved {len(df)} rows")
    else:
        print("No products passed the quality gate")


if __name__ == "__main__":
    main()
