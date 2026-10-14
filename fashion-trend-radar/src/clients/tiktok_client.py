import time
import requests
from config.settings import BRIGHTDATA_API_TOKEN

DATASET_ID = "gd_lu702nij2f790tmv9h"
SCRAPE_URL = "https://api.brightdata.com/datasets/v3/scrape"
SNAPSHOT_URL = "https://api.brightdata.com/datasets/v3/snapshot/{}"


class TikTokClient:
    """TikTok video discovery by keyword via Bright Data (async: trigger -> poll snapshot)."""

    def __init__(self, api_token=None, dataset_id=None):
        self.api_token = api_token or BRIGHTDATA_API_TOKEN
        self.dataset_id = dataset_id or DATASET_ID
        if not self.api_token:
            raise ValueError("BRIGHTDATA_API_TOKEN is missing. Put it in your .env file.")

    def search_keyword(self, keyword, limit=20, country="", poll_timeout=600, poll_interval=15):
        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
        params = {
            "dataset_id": self.dataset_id,
            "notify": "false",
            "include_errors": "true",
            "type": "discover_new",
            "discover_by": "keyword",
        }
        payload = {
            "input": [{"search_keyword": keyword, "country": country}],
            "limit_per_input": limit,
        }

        r = requests.post(SCRAPE_URL, headers=headers, params=params, json=payload, timeout=120)
        r.raise_for_status()
        snapshot_id = r.json()["snapshot_id"]

        snapshot_url = SNAPSHOT_URL.format(snapshot_id)
        deadline = time.time() + poll_timeout
        while time.time() < deadline:
            try:
                resp = requests.get(snapshot_url, headers=headers, params={"format": "json"}, timeout=60)
            except requests.exceptions.RequestException:
                time.sleep(poll_interval)
                continue
            if resp.status_code == 200 and resp.text.strip():
                return resp.json()
            time.sleep(poll_interval)
        raise TimeoutError(f"TikTok snapshot {snapshot_id} not ready after {poll_timeout}s")
