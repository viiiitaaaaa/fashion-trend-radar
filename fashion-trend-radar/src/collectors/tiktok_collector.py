from src.clients.tiktok_client import TikTokClient


class TikTokCollector:
    def __init__(self):
        self.client = TikTokClient()

    def fetch_keyword_data(self, keyword, limit=20, country=""):
        return self.client.search_keyword(keyword, limit=limit, country=country)
