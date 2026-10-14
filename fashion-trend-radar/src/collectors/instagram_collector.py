from src.clients.instagram_client import InstagramClient


class InstagramCollector:
    def __init__(self):
        self.client = InstagramClient()

    def fetch_urls(self, urls):
        return self.client.fetch_posts(urls)
