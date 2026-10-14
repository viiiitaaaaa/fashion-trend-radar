"""
Глубокая выборка по одному запросу: 30 страниц AliExpress через Dolphin
(профиль 859648353), цена $10-60 фильтруется прямо в URL AliExpress,
на выходе -- только товары с продажами > 30 и рейтингом > 4.5, с фото.

    python run_plaid_skirt_deep.py
"""
from config.settings import EXPORT_DIR
from src.collectors.aliexpress_collector import AliExpressCollector
from src.processors.aliexpress_filter import filter_products
from src.storage.files import save_csv, timestamp

KEYWORD = "plaid skirt"
SEARCH_TEXT = "women's plaid skirt"
PAGES = 30


def main():
    collector = AliExpressCollector()
    print(f"Fetching {PAGES} pages for {SEARCH_TEXT!r} ...")
    rows = collector.fetch_keyword_data(
        keyword=KEYWORD,
        limit=60,
        search_text=SEARCH_TEXT,
        min_price=10,
        max_price=60,
        pages=PAGES,
    )
    print(f"Total unique products across {PAGES} pages: {len(rows)}")

    kept = filter_products(rows, min_rating=4.5, min_price=10, max_price=60, min_orders=30)
    print(f"Passed rating>4.5 / $10<=price<=$60 / orders>30: {len(kept)}")

    ts = timestamp()
    out_path = f"{EXPORT_DIR}/plaid_skirt_deep_{ts}.csv"
    import pandas as pd
    save_csv(pd.DataFrame(kept), out_path)
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
