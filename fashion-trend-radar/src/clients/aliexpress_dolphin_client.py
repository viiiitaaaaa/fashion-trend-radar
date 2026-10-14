"""
AliExpress product search via the Dolphin{anty} antidetect browser (NOT Bright
Data) -- per user rule: AliExpress goes only through the antidetect browser.
Reuses C:\\Users\\User\\dolphin_anty\\dolphin.py (DolphinLocal / start_with_retry).
Desktop version only, .com only (never .ru) -- see dolphin-shots skill notes.
"""
import random
import sys
import time
import urllib.parse

sys.path.insert(0, r"C:\Users\User\dolphin_anty")
from dolphin import DolphinLocal, start_with_retry  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PROFILE = 859648353


def _human_pause(a=0.6, b=1.6):
    time.sleep(random.uniform(a, b))


def _autoscroll(page, steps=8, pause=0.4):
    for _ in range(steps):
        page.mouse.wheel(0, random.uniform(250, 450))
        time.sleep(pause + random.uniform(0, 0.3))


def search_keyword(keyword, limit=20, timeout_ms=60000, search_text=None,
                    min_price=15, max_price=60, apply_filters=True, apply_rating_filter=False, page=1):
    """Applies the min/max price range directly on the initial search request,
    as URL query params (minPrice/maxPrice). The "Quality & trust" (4 stars &
    up) rating filter (selectedSwitches=filterCode:4StarRating) is OFF by
    default -- pass apply_rating_filter=True to turn it back on.

    IMPORTANT: do NOT click the "Quality & trust" checkbox in-page after load.
    Confirmed by testing: clicking it triggers an SPA navigation that rebuilds
    the URL from the page's own filter state and silently DROPS minPrice/
    maxPrice from it (even though the sidebar's Min/Max inputs keep showing
    the old values) -- the resulting product list is unfiltered by price.
    Passing selectedSwitches on the very first URL avoids that reset entirely
    and applies both filters together in one request.
    """
    params = {
        "SearchText": search_text or keyword,
        "g": "y",
    }
    if page and page > 1:
        params["page"] = page
    if apply_filters:
        params["minPrice"] = int(min_price)
        params["maxPrice"] = int(max_price)
        if apply_rating_filter:
            params["selectedSwitches"] = "filterCode:4StarRating"
    url = "https://www.aliexpress.com/wholesale?" + urllib.parse.urlencode(params)

    api = DolphinLocal(port=DolphinLocal.discover() or 3001)
    data = start_with_retry(api, PROFILE, no_tabs=True)
    auto = data["automation"]

    results = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"ws://127.0.0.1:{auto['port']}{auto['wsEndpoint']}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

        if ".ru" in page.url:
            raise RuntimeError(f"Geo-redirected to .ru for keyword {keyword!r}: {page.url}")

        page.wait_for_selector('a[href*="/item/"]', timeout=timeout_ms)
        _human_pause(1.5, 3.0)

        _autoscroll(page)

        cards = page.query_selector_all('div[class*="search-item-card-wrapper"]')
        if not cards:
            cards = page.query_selector_all('a[href*="/item/"]')

        seen_links = set()
        for card in cards:
            link_el = card if card.get_attribute("href") else card.query_selector('a[href*="/item/"]')
            if not link_el:
                continue
            href = link_el.get_attribute("href") or ""
            if not href or "/item/" not in href:
                continue
            href = href.split("?")[0]
            if href.startswith("//"):
                href = "https:" + href
            if href in seen_links:
                continue
            seen_links.add(href)

            title_el = card.query_selector('[class*="us--title--"]')
            title = (title_el.get_attribute("title") if title_el else None) or ""

            price_el = card.query_selector('[class*="us--price--"]')
            price = (price_el.get_attribute("aria-label") if price_el else None) or None

            orders_el = card.query_selector('[class*="us--trade--"]')
            orders = orders_el.inner_text().strip() if orders_el else None

            rating_el = card.query_selector('[class*="starRating"]')
            rating = rating_el.inner_text().strip() if rating_el else None

            img_el = card.query_selector("img")
            image = img_el.get_attribute("src") or img_el.get_attribute("data-src") if img_el else None

            results.append({
                "keyword": keyword,
                "title": title,
                "price": price,
                "orders": orders,
                "rating": rating,
                "url": href,
                "image": image,
            })
            if len(results) >= limit:
                break

        page.close()
        browser.close()

    return results
