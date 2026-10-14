"""
Targeted AliExpress sourcing based on trend-radar related-queries analytics:
searches the winning attribute COMBINATIONS (length+color, fabric, rising
adjacent format) per keyword, instead of the plain base keyword.
"""
import time
import pandas as pd
from config.settings import EXPORT_DIR
from src.collectors.aliexpress_collector import AliExpressCollector
from src.processors.aliexpress_filter import filter_products
from src.storage.files import save_csv, timestamp

COMBOS = [
    ("plaid skirt",         "women's plaid skirt midi blue"),
    ("plaid skirt",         "women's wool plaid skirt"),
    ("funnel neck sweater", "women's funnel neck jacket"),
    ("funnel neck sweater", "women's mock neck sweatshirt"),
    ("chunky sweater",      "women's chunky sweater cream"),
    ("chunky sweater",      "women's chunky wool sweater"),
]

def main():
    collector = AliExpressCollector()
    ts = timestamp()
    all_rows = []
    for i, (keyword, search_text) in enumerate(COMBOS):
        print(f"[{i + 1}/{len(COMBOS)}] {keyword}  (search: {search_text!r})")
        if i > 0:
            time.sleep(5)
        try:
            rows = collector.fetch_keyword_data(keyword=keyword, limit=25, search_text=search_text)
        except Exception as e:
            print(f"  failed: {e}")
            continue
        kept = filter_products(rows, min_rating=4.0, min_price=15.0, max_price=60.0)
        for r in kept:
            r["combo"] = search_text
        print(f"  found {len(rows)} products, {len(kept)} passed rating>4 / $15<=price<=$60 / has sales+reviews")
        all_rows.extend(kept)
    if all_rows:
        df = pd.DataFrame(all_rows)
        out_path = f"{EXPORT_DIR}/aliexpress_combos_{ts}.csv"
        save_csv(df, out_path)
        print(f"Saved {len(df)} rows -> {out_path}")
    else:
        print("No products passed the quality gate")

if __name__ == "__main__":
    main()
