"""
Canonical Google Trends collector for this project (supersedes earlier
CSV-cache drafts). Parquet cache, TTL scales with window size, full-jitter
exponential backoff with a longer cap specifically on 429. Never routes
around a 429 (no proxy rotation, no header spoofing) -- it backs off and,
after max_attempts, gives up on that keyword for this run so the rest of
the batch keeps going. See TZ_trend_scoring.md for the fetch cadence
(bootstrap 730d once per keyword, weekly 730d refresh, daily 30-90d for
watchlist only).
"""

from __future__ import annotations

import random
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from pytrends.request import TrendReq


CACHE_DIR = Path("data/cache/google_trends")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def safe_slug(value: str) -> str:
    return (
        value.lower()
        .strip()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )


def make_timeframe(days: int) -> str:
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    return f"{start_date.isoformat()} {end_date.isoformat()}"


def cache_path(keyword: str, geo: str, days: int) -> Path:
    filename = f"{safe_slug(keyword)}__{geo}__{days}d.parquet"
    return CACHE_DIR / filename


def cache_is_fresh(path: Path, ttl_hours: int) -> bool:
    if not path.exists():
        return False

    age_seconds = time.time() - path.stat().st_mtime
    return age_seconds < ttl_hours * 3600


def get_ttl_hours(days: int) -> int:
    """Более длинную историю обновляем реже."""
    if days >= 365:
        return 24 * 7

    if days >= 90:
        return 24

    return 12


def create_client() -> TrendReq:
    return TrendReq(
        hl="en-US",
        tz=360,
        timeout=(10, 30),
        retries=0,
        backoff_factor=0,
    )


def normalize_google_trends_response(
    df: pd.DataFrame,
    keyword: str,
    geo: str,
    timeframe_days: int
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "date", "keyword", "market", "interest",
                "is_partial", "timeframe_days", "collected_at",
            ]
        )

    data = df.reset_index().copy()

    data = data.rename(
        columns={keyword: "interest", "isPartial": "is_partial"}
    )

    if "is_partial" not in data.columns:
        data["is_partial"] = False

    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["interest"] = pd.to_numeric(data["interest"], errors="coerce").fillna(0)

    data["keyword"] = keyword
    data["market"] = geo
    data["timeframe_days"] = timeframe_days
    data["collected_at"] = datetime.now(timezone.utc).isoformat()

    return data[
        ["date", "keyword", "market", "interest",
         "is_partial", "timeframe_days", "collected_at"]
    ]


def request_interest_over_time(keyword: str, geo: str, days: int) -> pd.DataFrame:
    client = create_client()

    client.build_payload(
        kw_list=[keyword],
        timeframe=make_timeframe(days),
        geo=geo,
        gprop="",
    )

    raw_df = client.interest_over_time()

    return normalize_google_trends_response(
        df=raw_df, keyword=keyword, geo=geo, timeframe_days=days,
    )


def is_rate_limit_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in ["429", "too many requests", "rate limit"])


def fetch_with_exponential_backoff(
    keyword: str,
    geo: str,
    days: int,
    max_attempts: int = 4,
    base_delay_seconds: float = 45,
    max_delay_seconds: float = 900,
) -> pd.DataFrame:
    """
    Full jitter: delay = random(0, min(max_delay, base * 2**attempt * mult)).
    На 429 множитель кратно больше -- мы ждём дольше, не повторяем чаще.
    """
    last_error = None

    for attempt in range(max_attempts):
        try:
            return request_interest_over_time(keyword=keyword, geo=geo, days=days)

        except Exception as error:
            last_error = error

            if attempt == max_attempts - 1:
                break

            multiplier = 2 ** attempt

            if is_rate_limit_error(error):
                cap = min(max_delay_seconds, base_delay_seconds * multiplier * 4)
            else:
                cap = min(max_delay_seconds, base_delay_seconds * multiplier)

            wait_seconds = random.uniform(0, cap)

            print(f"[{keyword}] failed: {error}. Retrying in {wait_seconds:.0f}s.")
            time.sleep(wait_seconds)

    raise RuntimeError(
        f"Google Trends unavailable for '{keyword}'. Last error: {last_error}"
    )


def get_google_trends_cached(
    keyword: str,
    geo: str = "US",
    days: int = 730,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Возвращает данные из Parquet, если кэш свежий. Иначе делает один
    бережный запрос и обновляет кэш."""
    path = cache_path(keyword=keyword, geo=geo, days=days)
    ttl_hours = get_ttl_hours(days)

    if not force_refresh and cache_is_fresh(path, ttl_hours):
        return pd.read_parquet(path)

    result = fetch_with_exponential_backoff(keyword=keyword, geo=geo, days=days)

    result.to_parquet(path, engine="pyarrow", compression="snappy", index=False)

    return result


def merge_google_trends_history(
    historical_df: pd.DataFrame,
    recent_df: pd.DataFrame
) -> pd.DataFrame:
    """Объединяет 730d и 30-90d снимки, убирая дубли по date+keyword+market
    (более свежий collected_at побеждает)."""
    combined = pd.concat([historical_df, recent_df], ignore_index=True)

    combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
    combined["collected_at"] = pd.to_datetime(
        combined["collected_at"], errors="coerce", utc=True
    )

    combined = (
        combined
        .sort_values("collected_at")
        .drop_duplicates(subset=["date", "keyword", "market"], keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )

    return combined


def collect_sequentially(
    keywords: list[str],
    geo: str = "US",
    days: int = 730,
    base_delay_seconds: tuple[float, float] = (15, 35),
) -> pd.DataFrame:
    """Последовательный bootstrap по списку keywords. Не запускай
    ThreadPoolExecutor/asyncio для pytrends запросов."""
    collected = []

    for index, keyword in enumerate(keywords, start=1):
        print(f"[{index}/{len(keywords)}] {keyword}")

        try:
            df = get_google_trends_cached(keyword=keyword, geo=geo, days=days)
            collected.append(df)
        except RuntimeError as error:
            print(f"SKIPPED: {error}")

        if index < len(keywords):
            time.sleep(random.uniform(*base_delay_seconds))

    if not collected:
        return pd.DataFrame()

    return pd.concat(collected, ignore_index=True)


# ---------------------------------------------------------------------------
# Related queries (RISING) -- the candidate-discovery step: give Google a
# broad seed ("skirt"), get back the refinements that are growing fastest.
# Same cache + backoff rules as interest_over_time above.
# ---------------------------------------------------------------------------

def related_cache_path(seed: str, geo: str, days: int) -> Path:
    return CACHE_DIR / f"related__{safe_slug(seed)}__{geo}__{days}d.parquet"


def request_related_queries(seed: str, geo: str, days: int) -> pd.DataFrame:
    client = create_client()
    client.build_payload(kw_list=[seed], timeframe=make_timeframe(days), geo=geo, gprop="")

    rq = client.related_queries() or {}
    rising = (rq.get(seed) or {}).get("rising")

    cols = ["seed", "query", "value", "is_breakout", "market", "timeframe_days", "collected_at"]
    if rising is None or rising.empty:
        return pd.DataFrame(columns=cols)

    data = rising.rename(columns={"query": "query", "value": "value"}).copy()
    data["value"] = pd.to_numeric(data["value"], errors="coerce").fillna(0)
    # Google shows "Breakout" for >5000% growth; pytrends returns it as a big number.
    data["is_breakout"] = data["value"] >= 5000
    data["seed"] = seed
    data["market"] = geo
    data["timeframe_days"] = days
    data["collected_at"] = datetime.now(timezone.utc).isoformat()
    return data[cols]


def get_related_queries_cached(
    seed: str,
    geo: str = "US",
    days: int = 90,
    max_attempts: int = 4,
    base_delay_seconds: float = 45,
    max_delay_seconds: float = 900,
) -> pd.DataFrame:
    path = related_cache_path(seed, geo, days)
    if cache_is_fresh(path, 24 * 7):  # related queries: weekly is enough
        return pd.read_parquet(path)

    last_error = None
    for attempt in range(max_attempts):
        try:
            result = request_related_queries(seed, geo, days)
            result.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
            return result
        except Exception as error:
            last_error = error
            if attempt == max_attempts - 1:
                break
            mult = 4 if is_rate_limit_error(error) else 1
            cap = min(max_delay_seconds, base_delay_seconds * (2 ** attempt) * mult)
            wait = random.uniform(0, cap)
            print(f"[{seed}] related failed: {error}. Retrying in {wait:.0f}s.")
            time.sleep(wait)

    raise RuntimeError(f"Related queries unavailable for '{seed}'. Last error: {last_error}")
