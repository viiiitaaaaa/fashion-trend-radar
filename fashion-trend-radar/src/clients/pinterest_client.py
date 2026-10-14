import json
import time
import requests
from config.settings import BRIGHTDATA_API_TOKEN

DATASET_ID = "gd_lk0sjs4d21kdr7cnlv"
SCRAPE_URL = "https://api.brightdata.com/datasets/v3/scrape"


class PinterestClient:
    def __init__(self, api_token=None, dataset_id=None):
        self.api_token = api_token or BRIGHTDATA_API_TOKEN
        self.dataset_id = dataset_id or DATASET_ID

        if not self.api_token:
            raise ValueError("BRIGHTDATA_API_TOKEN is missing. Put it in your .env file.")

    def search_keyword(self, keyword, limit=20, timeout=180):
        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
        params = {
            "dataset_id": self.dataset_id,
            "notify": "false",
            "include_errors": "true",
            "type": "discover_new",
            "discover_by": "keyword",
        }
        payload = {"input": [{"keyword": keyword}], "limit_per_input": limit}

        last_err = None
        for attempt in range(3):
            try:
                r = requests.post(SCRAPE_URL, headers=headers, params=params, json=payload, timeout=timeout)
                r.raise_for_status()
                last_err = None
                break
            except requests.exceptions.RequestException as e:
                last_err = e
                time.sleep(10)
        if last_err:
            raise last_err

        rows = []
        for line in r.text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows
