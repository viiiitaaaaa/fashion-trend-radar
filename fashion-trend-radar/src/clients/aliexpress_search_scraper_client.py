"""
AliExpress product search via the Apify actor axlymxp/aliexpress-search-scraper
(https://console.apify.com/actors/uNGAIgYARPCnogDTx) -- unlike
aliexpress_apify_client.py (devcake actor), this one genuinely paginates:
maxItemsPerQuery scrapes real AliExpress result pages (60 products/page) up to
3600, and returns ready-made numeric rating/orders/price fields (no text
parsing needed).

Pricing (pay-per-event, checked 15.09.2026): $0.003 per product row returned
+ $0.01 actor-start fee. ~$3/1000 products.

Auth: APIFY_API_TOKEN in .env / config/settings.py.
"""
import requests

from config.settings import APIFY_API_TOKEN

ACTOR_ID = "axlymxp~aliexpress-search-scraper"
RUN_SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"


def search_keyword(keyword, max_items=180, search_text=None, sort="default",
                    region="US", currency="USD", min_price=None, max_price=None, timeout=600):
    """One search query -> list of raw actor rows (rating, orders, price are
    already numeric). `max_items` is clamped to the actor's own bounds
    (1-3600, 60 products per AliExpress page)."""
    if not APIFY_API_TOKEN:
        raise RuntimeError("APIFY_API_TOKEN not set in .env")

    payload = {
        "searchQueries": [search_text or keyword],
        "maxItemsPerQuery": max(1, min(int(max_items), 3600)),
        "sort": sort,
        "region": region,
        "currency": currency,
    }

    r = requests.post(RUN_SYNC_URL, params={"token": APIFY_API_TOKEN}, json=payload, timeout=timeout)
    r.raise_for_status()
    items = r.json()

    results = []
    for it in items:
        price = it.get("price")
        if min_price is not None and (price is None or price < min_price):
            continue
        if max_price is not None and (price is None or price > max_price):
            continue
        results.append({
            "keyword": keyword,
            "title": it.get("title") or "",
            "price": price,
            "orders": it.get("orders") or 0,
            "orders_text": it.get("orders_text"),
            "rating": it.get("rating"),
            "url": it.get("url") or "",
            "image": it.get("image"),
            "is_choice": it.get("is_choice"),
        })
    return results
