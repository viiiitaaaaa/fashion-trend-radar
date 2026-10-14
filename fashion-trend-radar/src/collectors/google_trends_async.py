"""
Async wrapper around the sync pytrends client (Google_SEMAPHORE=1): asyncio
here manages the queue/backoff/cache-check without blocking the rest of the
pipeline, it does NOT increase real concurrency to Google -- exactly one
request in flight at a time, same as the sequential collector. See
src/collectors/google_trends_cached.py for the on-disk Parquet cache this
shares conventions with (same cache_path/is_rate_limit_error logic,
duplicated here in async form rather than imported to keep this file
runnable standalone).
"""

from __future__ import annotations

import asyncio
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from pytrends.request import TrendReq


CACHE_ROOT = Path("data/cache/google_trends")
CACHE_ROOT.mkdir(parents=True, exist_ok=True)

# Только 1 запрос одновременно к Google Trends.
GOOGLE_SEMAPHORE = asyncio.Semaphore(1)


def is_rate_limit_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        token in message
        for token in ["429", "too many requests", "rate limit"]
    )


def timeframe(days: int) -> str:
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    return f"{start_date.isoformat()} {end_date.isoformat()}"


def fetch_pytrends_sync(keyword: str, geo: str, days: int, gprop: str = "") -> pd.DataFrame:
    client = TrendReq(
        hl="en-US",
        tz=360,
        timeout=(10, 30),
        retries=0,
        backoff_factor=0,
    )

    client.build_payload(
        kw_list=[keyword],
        timeframe=timeframe(days),
        geo=geo,
        gprop=gprop,  # "" = web search, "youtube" = YouTube search
    )

    raw = client.interest_over_time()

    if raw.empty:
        return pd.DataFrame(
            columns=["date", "keyword", "region", "interest", "is_partial"]
        )

    data = raw.reset_index().rename(
        columns={keyword: "interest", "isPartial": "is_partial"}
    )

    if "is_partial" not in data.columns:
        data["is_partial"] = False

    data["keyword"] = keyword
    data["region"] = geo
    data["date"] = pd.to_datetime(data["date"])

    return data[["date", "keyword", "region", "interest", "is_partial"]]


def backoff_delay(
    attempt: int,
    base_seconds: float = 30,
    max_seconds: float = 900,
    rate_limited: bool = False,
) -> float:
    """
    Full jitter. Обычная ошибка: random(0, base * 2^attempt).
    429: random(0, base * 4 * 2^attempt) -- длинная пауза лучше, чем
    быстрые повторы, которые только продлевают блокировку.
    """
    multiplier = 4 if rate_limited else 1
    ceiling = min(max_seconds, base_seconds * multiplier * (2 ** attempt))
    return random.uniform(0, ceiling)


async def fetch_with_backoff(
    keyword: str,
    geo: str = "US",
    days: int = 90,
    max_attempts: int = 4,
    gprop: str = "",
) -> pd.DataFrame:
    last_error = None

    for attempt in range(max_attempts):
        try:
            async with GOOGLE_SEMAPHORE:
                result = await asyncio.to_thread(
                    fetch_pytrends_sync, keyword, geo, days, gprop,
                )

            # Небольшой gap даже после успешного запроса.
            await asyncio.sleep(random.uniform(10, 25))
            return result

        except Exception as error:
            last_error = error

            if attempt == max_attempts - 1:
                break

            delay = backoff_delay(
                attempt=attempt,
                rate_limited=is_rate_limit_error(error),
            )

            print(f"[{keyword}] error: {error}. Retry in {delay:.0f}s.")
            await asyncio.sleep(delay)

    raise RuntimeError(f"Failed for '{keyword}'. Last error: {last_error}")


async def collect_keywords(
    keywords: list[str],
    geo: str = "US",
    days: int = 90,
    gprop: str = "",
) -> pd.DataFrame:
    """Задачи создаются асинхронно, но Semaphore(1) не даёт им бомбить
    Google одновременно -- одна и та же гарантия, что и у sequential
    collect_sequentially() в google_trends_cached.py, другая форма записи."""
    tasks = [
        fetch_with_backoff(keyword=keyword, geo=geo, days=days, gprop=gprop)
        for keyword in keywords
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_frames = []

    for keyword, result in zip(keywords, results):
        if isinstance(result, Exception):
            print(f"SKIPPED {keyword}: {result}")
        else:
            valid_frames.append(result)

    if not valid_frames:
        return pd.DataFrame()

    return pd.concat(valid_frames, ignore_index=True)
