"""
AliExpress product search via the Apify actor devcake/aliexpress-products-scraper
(https://console.apify.com/actors/dky0rE40JOyXui6TR) -- a SEPARATE, independent
source from src/clients/aliexpress_dolphin_client.py. Per user rule, the
Dolphin-based client stays as the default/primary AliExpress source; this one
is opt-in (run_aliexpress_apify.py) for when the antidetect-browser path is
too slow/flaky (memory crashes, captcha) to bother with.

Auth: APIFY_API_TOKEN in .env / config/settings.py.

Actor input schema (fetched from the actor's build metadata, 15.09.2026):
  searchQueries: list[str]   -- required if productUrls not given
  productUrls:   list[str]
  maxProducts:   int, 50-1000, default 50   (50 is the actor's own minimum)
  sortBy:        "default" | "price_asc" | "price_desc" | "orders"

Dataset item shape (from a live test run, 15.09.2026):
  productId, title, productUrl, searchQuery, scrapedAt, imageUrl,
  priceCurrent, priceCurrentMin, priceCurrentMax, priceOriginal*,
  priceDiscount, priceCurrency, ratingValue, reviewCount, soldCount,
  soldDescription (e.g. "3,000+ sold"), tags

Normalizes to the SAME row shape as aliexpress_dolphin_client.search_keyword
(keyword, title, price, orders, rating, url, image) so it's a drop-in
replacement for src/processors/aliexpress_filter.filter_products.
"""
import requests

from config.settings import APIFY_API_TOKEN

ACTOR_ID = "devcake~aliexpress-products-scraper"
RUN_SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"


def search_keyword(keyword, limit=50, search_text=None, sort_by="orders", timeout=300):
    """One search query -> list of normalized product rows. `limit` is clamped
    to the actor's own bounds (50-1000)."""
    if not APIFY_API_TOKEN:
        raise RuntimeError("APIFY_API_TOKEN not set in .env")

    max_products = max(50, min(int(limit), 1000))
    payload = {
        "searchQueries": [search_text or keyword],
        "maxProducts": max_products,
        "sortBy": sort_by,
    }

    r = requests.post(
        RUN_SYNC_URL,
        params={"token": APIFY_API_TOKEN},
        json=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    items = r.json()

    results = []
    for it in items:
        price = it.get("priceCurrent") or (
            f"{it.get('priceCurrency', '$')}{it.get('priceCurrentMin')}"
            if it.get("priceCurrentMin") is not None else None
        )
        results.append({
            "keyword": keyword,
            "title": it.get("title") or "",
            "price": price,
            "orders": it.get("soldDescription") or (
                f"{it.get('soldCount')} sold" if it.get("soldCount") else None
            ),
            "rating": it.get("ratingValue"),
            "url": it.get("productUrl") or "",
            "image": it.get("imageUrl"),
        })
        if len(results) >= limit:
            break
    return results
