import time
import requests
from config.settings import BRIGHTDATA_API_TOKEN

COLLECTOR_ID = "c_mtyj2z3e14ur8nhivi"
TRIGGER_URL = "https://api.brightdata.com/dca/trigger"
DATASET_URL = "https://api.brightdata.com/dca/dataset"


class BrightDataClient:
    def __init__(self, api_token=None, collector=None):
        self.api_token = api_token or BRIGHTDATA_API_TOKEN
        self.collector = collector or COLLECTOR_ID

        if not self.api_token:
            raise ValueError("BRIGHTDATA_API_TOKEN is missing. Put it in your .env file.")

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

    def trigger(self, target_url):
        r = requests.post(
            TRIGGER_URL,
            headers=self._headers(),
            params={"collector": self.collector, "queue_next": 1},
            json=[{"url": target_url}],
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["collection_id"]

    def fetch_result(self, collection_id, max_wait=300, poll_interval=10):
        headers = {"Authorization": f"Bearer {self.api_token}"}
        waited = 0
        while waited < max_wait:
            # 14.10: обрыв на опросе не роняет уже оплаченный сбор — ждём и спрашиваем снова.
            # trigger() не повторяем сам: повторный запуск платный (Newman — повтор не должен списывать дважды)
            try:
                r = requests.get(f"{DATASET_URL}?id={collection_id}", headers=headers, timeout=30)
            except (requests.ConnectionError, requests.Timeout):
                time.sleep(poll_interval)
                waited += poll_interval
                continue
            if r.status_code == 200 and r.text.strip() not in ("", "[]"):
                return r.json()
            time.sleep(poll_interval)
            waited += poll_interval
        raise TimeoutError(f"Bright Data collection {collection_id} not ready after {max_wait}s")

    def fetch_url(self, target_url):
        collection_id = self.trigger(target_url)
        result = self.fetch_result(collection_id)
        return result[0] if isinstance(result, list) and result else result
