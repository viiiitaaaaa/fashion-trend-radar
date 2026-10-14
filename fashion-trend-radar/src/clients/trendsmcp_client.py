"""
trendsmcp.ai client (third-party trends API, free plan: 100 requests/month,
90 days of history, top-10 on boards). Key: TRENDSMCP_API_KEY in .env.
Every successful call is appended to data/logs/trendsmcp_usage.csv so the
monthly quota is visible; raw answers go to data/raw/trendsmcp/.
Data provenance is not disclosed by the vendor -- validate against our own
Google Trends before trusting other sources.
"""
import csv
import json
from datetime import datetime
from pathlib import Path

import requests

API = "https://api.trendsmcp.ai/api"
FREE_MONTHLY = 100
RAW = Path("data/raw/trendsmcp")
LOG = Path("data/logs/trendsmcp_usage.csv")


def _key():
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("TRENDSMCP_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("Нет TRENDSMCP_API_KEY в .env")


def used_this_month():
    if not LOG.exists():
        return 0
    month = datetime.now().strftime("%Y-%m")
    with LOG.open(encoding="utf-8") as f:
        return sum(1 for row in csv.DictReader(f) if row["time"].startswith(month) and row["ok"] == "1")


def call(body: dict) -> dict:
    if used_this_month() >= FREE_MONTHLY:
        raise RuntimeError(f"Бесплатная квота {FREE_MONTHLY} запросов в этом месяце исчерпана")
    r = requests.post(API, headers={"Authorization": _key()}, json=body, timeout=60)
    try:
        data = r.json()
    except ValueError:
        data = {"raw_text": r.text[:2000]}
    # errors can come wrapped in HTTP 200: {"statusCode": 400, "body": "{\"error\": ...}"}
    status = data.get("statusCode", r.status_code) if isinstance(data, dict) else r.status_code
    ok = 200 <= r.status_code < 300 and 200 <= int(status) < 300
    RAW.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    with LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "ok", "status", "body"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), int(ok), status,
                    json.dumps(body, ensure_ascii=False)])
    name = "_".join(str(body.get(k, "")) for k in ("mode", "source", "keyword", "type", "category")).strip("_")
    (RAW / f"{datetime.now():%Y%m%d_%H%M%S}_{name.replace(' ', '-')[:80]}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if not ok:
        raise RuntimeError(f"HTTP {status}: {str(data)[:300]}")
    return data


def rows(data) -> list:
    """time_series answer -> list of {date, value, ...} (body arrives as a JSON string)."""
    if isinstance(data, dict) and "body" in data:
        data = json.loads(data["body"]) if isinstance(data["body"], str) else data["body"]
    return data if isinstance(data, list) else []


def time_series(source: str, keyword: str) -> dict:
    return call({"mode": "get_time_series", "source": source, "keyword": keyword})


def growth(source: str, keyword: str, windows=("30D", "3M")) -> dict:
    # windows: 7D 14D 30D 3M 6M 12M 24M MTD QTD YTD; all windows in one call = 1 request
    return call({"mode": "get_growth", "source": source, "keyword": keyword, "percent_growth": list(windows)})


def top_trends(type_: str, category: str | None = None, limit: int = 10) -> dict:
    body = {"mode": "get_top_trends", "type": type_, "limit": limit}
    if category:
        body["category"] = category
    return call(body)
