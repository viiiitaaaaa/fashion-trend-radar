from src.clients.pinterest_client import PinterestClient


class PinterestCollector:
    def __init__(self):
        self.client = PinterestClient()

    def fetch_keyword_data(self, keyword, limit=20):
        return self.client.search_keyword(keyword, limit=limit)
