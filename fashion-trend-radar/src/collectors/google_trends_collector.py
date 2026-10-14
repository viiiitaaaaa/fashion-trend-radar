from urllib.parse import urlencode
from src.clients.brightdata_client import BrightDataClient
from config.settings import DEFAULT_GEO, DEFAULT_HL, DEFAULT_TIMEFRAME


class GoogleTrendsCollector:
    BASE_TRENDS_URL = "https://trends.google.com/trends/explore"

    def __init__(self):
        self.client = BrightDataClient()

    def build_url(self, keyword, geo=DEFAULT_GEO, hl=DEFAULT_HL, timeframe=DEFAULT_TIMEFRAME, category=None):
        params = {
            "q": keyword,
            "geo": geo,
            "hl": hl,
            "date": timeframe,
        }

        return f"{self.BASE_TRENDS_URL}?{urlencode(params)}"

    def fetch_keyword_data(self, keyword, geo=DEFAULT_GEO, hl=DEFAULT_HL, timeframe=DEFAULT_TIMEFRAME, category=None):
        url = self.build_url(keyword=keyword, geo=geo, hl=hl, timeframe=timeframe, category=category)
        return self.client.fetch_url(url)
