"""
Keyword Tool API v2 client (https://api.keywordtool.io) -- candidate discovery
across TikTok/Pinterest/Amazon/Etsy/Reddit/Google Trends suggestions, plus
exact Google search volume (12-48 monthly points) for validation.

Budget-first: the daily request pool is tiny (Starter = 50/24h, shared with
the web UI and MCP) and bursts are capped at 15/min. So:
  - every response is cached on disk; an identical request is served from
    cache and never spends quota again (TTL: suggestions 7d, volume 30d);
  - requests are spaced >= 4.5s apart (stays under 15/min);
  - quota() lets a runner check what's left before spending it;
  - volume() batches up to 1000 keywords per request -- always batch.

API key: KEYWORDTOOL_API_KEY in .env (never hard-coded, never logged).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://api.keywordtool.io/v2"
SANDBOX = "https://api.keywordtool.io/v2-sandbox"
CACHE_DIR = Path("data/cache/keywordtool")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

US_LOCATION = 2840
MIN_GAP_SECONDS = 4.5
TTL_HOURS = {"suggestions": 24 * 7, "volume": 24 * 30}


class KeywordToolError(RuntimeError):
    pass


class KeywordToolClient:
    def __init__(self, api_key: str | None = None, sandbox: bool = False):
        self.api_key = api_key or os.getenv("KEYWORDTOOL_API_KEY")
        if not self.api_key:
            raise KeywordToolError("KEYWORDTOOL_API_KEY is missing in .env")
        self.base = SANDBOX if sandbox else BASE
        self._last_call = 0.0

    # -- plumbing -----------------------------------------------------------
    def _cache_file(self, mode: str, provider: str, payload: dict) -> Path:
        key_src = json.dumps({k: v for k, v in payload.items() if k != "apikey"},
                             sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha1(f"{self.base}|{mode}|{provider}|{key_src}".encode()).hexdigest()[:16]
        return CACHE_DIR / f"{mode}__{provider}__{digest}.json"

    def _post(self, mode: str, provider: str, payload: dict, use_cache: bool = True) -> dict:
        path = self._cache_file(mode, provider, payload)
        if use_cache and path.exists():
            age_h = (time.time() - path.stat().st_mtime) / 3600
            if age_h < TTL_HOURS.get(mode, 24):
                return json.loads(path.read_text(encoding="utf-8"))

        wait = MIN_GAP_SECONDS - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)

        body = {**payload, "apikey": self.api_key, "output": "json"}
        resp = requests.post(f"{self.base}/search/{mode}/{provider}", json=body, timeout=120)
        self._last_call = time.time()

        try:
            data = resp.json()
        except ValueError:
            raise KeywordToolError(f"{mode}/{provider}: HTTP {resp.status_code}, non-JSON body")

        if "error" in data:
            err = data["error"]
            raise KeywordToolError(f"{mode}/{provider}: code {err.get('code')} {err.get('message')}")

        # code 10 = incomplete results, not counted against quota -- don't cache
        # a partial answer; caller can retry immediately.
        if (data.get("notice") or {}).get("code") == 10:
            return data

        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    # -- public -------------------------------------------------------------
    def quota(self) -> dict:
        resp = requests.get(f"{self.base}/quota", params={"apikey": self.api_key}, timeout=30)
        return resp.json()

    def suggestions(
        self,
        keyword: str,
        provider: str = "google",
        country: str = "US",
        language: str = "en",
        type_: str = "suggestions",
        metrics: bool = False,
        exclude: list[str] | None = None,
        category: str | None = None,
    ) -> dict:
        payload = {
            "keyword": keyword,
            "country": country,
            "language": language,
            "type": type_,
            "metrics": metrics,
            "exclude": exclude or [],
        }
        if category:
            payload["category"] = category
        if metrics and provider in ("google", "bing"):
            payload.update({"metrics_location": [US_LOCATION], "metrics_language": ["en"],
                            "metrics_currency": "USD"})
        return self._post("suggestions", provider, payload)

    def volume(self, keywords: list[str], provider: str = "google") -> dict:
        """Up to 1000 keywords per request. Google/Bing = exact Keyword Planner
        numbers; other providers = Keyword Tool's own estimate."""
        keywords = [k for k in dict.fromkeys(k.strip() for k in keywords) if k][:1000]
        payload = {"keyword": keywords}
        if provider in ("google", "bing"):
            payload.update({"metrics_location": [US_LOCATION], "metrics_language": ["en"],
                            "metrics_currency": "USD"})
        if provider == "google":
            payload["metrics_network"] = "googlesearch"
        return self._post("volume", provider, payload)


def flatten_suggestions(data: dict, provider: str, seed: str) -> list[dict]:
    """results is {bucket: [ {string, volume?, ...}, ... ]} for suggestions."""
    rows = []
    for bucket, items in (data.get("results") or {}).items():
        for it in items or []:
            rows.append({
                "provider": provider,
                "seed": seed,
                "bucket": bucket,
                "keyword": it.get("string"),
                "volume": it.get("volume"),
                "trend": it.get("trend"),
                "cpc": it.get("cpc"),
                "cmp": it.get("cmp"),
            })
    return rows


def flatten_volume(data: dict) -> list[dict]:
    """results is {keyword: {string, volume, m1..m48, m1_month.., trend, cpc, cmp}}."""
    rows = []
    for kw, it in (data.get("results") or {}).items():
        months = []
        for i in range(1, 49):
            v = it.get(f"m{i}")
            y, m = it.get(f"m{i}_year"), it.get(f"m{i}_month")
            if y and m:
                months.append({"year": y, "month": m, "volume": v})
        rows.append({
            "keyword": it.get("string", kw),
            "volume": it.get("volume"),
            "trend": it.get("trend"),
            "cpc": it.get("cpc"),
            "cmp": it.get("cmp"),
            "monthly": months,
        })
    return rows
