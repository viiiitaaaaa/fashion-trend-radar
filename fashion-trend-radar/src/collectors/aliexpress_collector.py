import time

from src.clients.aliexpress_dolphin_client import search_keyword


class AliExpressCollector:
    def fetch_keyword_data(self, keyword, limit=20, search_text=None, min_price=15, max_price=60,
                            pages=1, page_pause=3):
        """Loops search_keyword over `pages` AliExpress result pages (page=1..pages),
        deduplicating by url. `limit` applies per page."""
        results = []
        seen_urls = set()
        for page in range(1, pages + 1):
            if page > 1:
                time.sleep(page_pause)
            rows = search_keyword(keyword, limit=limit, search_text=search_text,
                                   min_price=min_price, max_price=max_price, page=page)
            new_rows = [r for r in rows if r["url"] not in seen_urls]
            if page > 1 and not new_rows:
                break
            seen_urls.update(r["url"] for r in new_rows)
            results.extend(new_rows)
        return results
