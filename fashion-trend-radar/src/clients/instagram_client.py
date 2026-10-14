import json
import time
import requests
from config.settings import BRIGHTDATA_API_TOKEN


def _parse_body(text):
    """The snapshot download comes back either as one JSON array or as
    NDJSON (one JSON object per line) depending on batch size -- handle both."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows

DATASET_ID = "gd_lk5ns7kz21pck8jpis"
SCRAPE_URL = "https://api.brightdata.com/datasets/v3/scrape"
SNAPSHOT_URL = "https://api.brightdata.com/datasets/v3/snapshot/{}"


class InstagramClient:
    """Instagram post/Reel stats by URL via Bright Data (async: trigger -> poll
    snapshot). NOT keyword discovery -- this dataset only accepts direct post/
    Reel URLs ("It is not a post URL" for profile/hashtag/explore pages), so
    candidate URLs must come from elsewhere (web search, manual browsing)."""

    def __init__(self, api_token=None, dataset_id=None):
        self.api_token = api_token or BRIGHTDATA_API_TOKEN
        self.dataset_id = dataset_id or DATASET_ID
        if not self.api_token:
            raise ValueError("BRIGHTDATA_API_TOKEN is missing. Put it in your .env file.")

    def fetch_posts(self, urls, poll_timeout=300, poll_interval=10):
        if not urls:
            return []
        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
        params = {"dataset_id": self.dataset_id, "notify": "false", "include_errors": "true"}
        payload = {"input": [{"url": u} for u in urls]}

        r = requests.post(SCRAPE_URL, headers=headers, params=params, json=payload, timeout=120)
        r.raise_for_status()

        # Small batches sometimes come back synchronously (a plain body), others
        # return a snapshot_id to poll -- handle both.
        try:
            trigger_json = r.json()
        except ValueError:
            trigger_json = None
        if not (isinstance(trigger_json, dict) and "snapshot_id" in trigger_json):
            return _parse_body(r.text)
        snapshot_id = trigger_json["snapshot_id"]

        snapshot_url = SNAPSHOT_URL.format(snapshot_id)
        deadline = time.time() + poll_timeout
        while time.time() < deadline:
            try:
                resp = requests.get(snapshot_url, headers=headers, params={"format": "json"}, timeout=60)
            except requests.exceptions.RequestException:
                time.sleep(poll_interval)
                continue
            if resp.status_code == 200 and resp.text.strip():
                return _parse_body(resp.text)
            time.sleep(poll_interval)
        raise TimeoutError(f"Instagram snapshot {snapshot_id} not ready after {poll_timeout}s")
