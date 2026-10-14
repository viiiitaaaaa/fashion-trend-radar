import requests
from config.settings import BRIGHTDATA_API_TOKEN

url = "https://api.brightdata.com/datasets/v3/scrape"
headers = {"Authorization": f"Bearer {BRIGHTDATA_API_TOKEN}", "Content-Type": "application/json"}

target_url = "https://www.instagram.com/explore/search/keyword/?q=%23plaidskirt"

import time

for dataset_id in ["gd_l1vikfch901nx3by4"]:
    params = {"dataset_id": dataset_id, "notify": "false", "include_errors": "true"}
    body = {"input": [{"url": target_url}]}
    resp = requests.post(url, params=params, headers=headers, json=body, timeout=180)
    print(dataset_id, "trigger ->", resp.status_code, resp.text[:300])
    if resp.status_code == 202:
        snapshot_id = resp.json()["snapshot_id"]
        snap_url = f"https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}"
        for i in range(20):
            r2 = requests.get(snap_url, headers=headers, params={"format": "json"}, timeout=60)
            print(i, r2.status_code, len(r2.text), r2.text[:200])
            if r2.status_code == 200 and r2.text.strip():
                with open("_search_kw_result.json", "w", encoding="utf-8") as f:
                    f.write(r2.text)
                print("SAVED")
                break
            time.sleep(15)
