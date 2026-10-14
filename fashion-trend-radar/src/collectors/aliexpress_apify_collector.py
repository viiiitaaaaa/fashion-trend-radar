from src.clients.aliexpress_apify_client import search_keyword


class AliExpressApifyCollector:
    def fetch_keyword_data(self, keyword, limit=50, search_text=None, sort_by="orders"):
        return search_keyword(keyword, limit=limit, search_text=search_text, sort_by=sort_by)
