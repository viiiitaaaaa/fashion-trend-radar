"""
Глубокая выборка по одному запросу через Apify-актор axlymxp/aliexpress-search-scraper
(реально паджинирует, в отличие от devcake-актора) -- 20 "страниц" (1200 товаров)
по "women's plaid skirt", цена $10-60, на выходе только rating>4.5 и orders>30.

Cost: ~$0.003/item -> ~1200 * $0.003 + $0.01 start ~= $3.6-3.7

    python run_plaid_skirt_apify.py
"""
import pandas as pd
from config.settings import EXPORT_DIR
from src.clients.aliexpress_search_scraper_client import search_keyword
from src.storage.files import save_csv, timestamp

KEYWORD = "plaid skirt"
SEARCH_TEXT = "women's plaid skirt"
MAX_ITEMS = 1200  # 20 pages * 60


def main():
    print(f"Fetching up to {MAX_ITEMS} products for {SEARCH_TEXT!r} via Apify ...")
    rows = search_keyword(KEYWORD, max_items=MAX_ITEMS, search_text=SEARCH_TEXT,
                           sort="default", min_price=10, max_price=60)
    print(f"Total products (price $10-60): {len(rows)}")

    kept = [r for r in rows if (r["rating"] or 0) > 4.5 and (r["orders"] or 0) > 30]
    print(f"Passed rating>4.5 / orders>30: {len(kept)}")

    ts = timestamp()
    out_path = f"{EXPORT_DIR}/plaid_skirt_apify_{ts}.csv"
    save_csv(pd.DataFrame(kept), out_path)
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
