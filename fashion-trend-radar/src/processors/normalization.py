"""
Canonical event schema so scoring never touches source-specific JSON
directly. Add one normalize_<source>() adapter per new collector; keep
raw_payload so a schema change on the provider's side never loses data
that's already been paid for / rate-limited to collect.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import pandas as pd


CANONICAL_COLUMNS = [
    "observed_at",
    "source",
    "market",
    "keyword",
    "entity_type",
    "entity_id",
    "entity_name",

    "published_at",

    "views",
    "likes",
    "comments",
    "shares",
    "saves",

    "price",
    "rating",
    "review_count",
    "rank",

    "seller",
    "brand",

    "raw_payload",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_canonical_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=CANONICAL_COLUMNS)


def normalize_tiktok_video(
    item: dict[str, Any],
    keyword: str,
    market: str = "US"
) -> dict[str, Any]:
    """
    Адаптер: меняй ключи только здесь,
    если provider отдаёт другую JSON-схему.
    """
    return {
        "observed_at": utc_now_iso(),
        "source": "tiktok",
        "market": market,
        "keyword": keyword,
        "entity_type": "video",
        "entity_id": str(item.get("id", "")),
        "entity_name": item.get("username", ""),
        "published_at": item.get("create_time"),

        "views": int(item.get("view_count", 0) or 0),
        "likes": int(item.get("like_count", 0) or 0),
        "comments": int(item.get("comment_count", 0) or 0),
        "shares": int(item.get("share_count", 0) or 0),
        "saves": int(item.get("favorites_count", 0) or 0),

        "price": None,
        "rating": None,
        "review_count": None,
        "rank": None,

        "seller": None,
        "brand": None,

        "raw_payload": item,
    }


def normalize_amazon_product(
    item: dict[str, Any],
    keyword: str,
    market: str = "US"
) -> dict[str, Any]:
    return {
        "observed_at": utc_now_iso(),
        "source": "amazon",
        "market": market,
        "keyword": keyword,
        "entity_type": "product",
        "entity_id": str(item.get("asin", "")),
        "entity_name": item.get("title", ""),
        "published_at": None,

        "views": None,
        "likes": None,
        "comments": None,
        "shares": None,
        "saves": None,

        "price": item.get("price"),
        "rating": item.get("rating"),
        "review_count": item.get("review_count"),
        "rank": item.get("best_seller_rank"),

        "seller": item.get("seller"),
        "brand": item.get("brand"),

        "raw_payload": item,
    }


def normalize_google_trends(
    trends_df: pd.DataFrame,
    keyword: str,
    market: str = "US"
) -> pd.DataFrame:
    data = trends_df.copy()

    data = data.rename(
        columns={
            "date": "published_at",
            "interest": "views",
        }
    )

    data["observed_at"] = utc_now_iso()
    data["source"] = "google_trends"
    data["market"] = market
    data["keyword"] = keyword
    data["entity_type"] = "trend_point"
    data["entity_id"] = (
        keyword + "_" + data["published_at"].astype(str)
    )
    data["entity_name"] = keyword

    for col in [
        "likes", "comments", "shares", "saves",
        "price", "rating", "review_count", "rank",
        "seller", "brand", "raw_payload",
    ]:
        data[col] = None

    return data[CANONICAL_COLUMNS]


def aggregate_tiktok_daily(
    normalized_events: pd.DataFrame
) -> pd.DataFrame:
    data = normalized_events.copy()

    data = data[data["source"] == "tiktok"].copy()

    for col in ["views", "likes", "comments", "shares", "saves"]:
        data[col] = pd.to_numeric(
            data[col],
            errors="coerce",
        ).fillna(0)

    data["published_at"] = pd.to_datetime(
        data["published_at"],
        errors="coerce",
        utc=True,
    )

    data["engagement_rate"] = (
        (
            data["likes"]
            + data["comments"]
            + data["shares"]
            + data["saves"]
        )
        / data["views"].clip(lower=1)
    )

    data["shares_per_1k"] = (
        data["shares"]
        / data["views"].clip(lower=1)
        * 1000
    )

    data["saves_per_1k"] = (
        data["saves"]
        / data["views"].clip(lower=1)
        * 1000
    )

    aggregated = (
        data
        .groupby(["keyword", "market"], as_index=False)
        .agg(
            video_count=("entity_id", "nunique"),
            creator_count=("entity_name", "nunique"),
            views_total=("views", "sum"),
            views_median=("views", "median"),
            engagement_median=(
                "engagement_rate",
                "median",
            ),
            shares_per_1k_median=(
                "shares_per_1k",
                "median",
            ),
            saves_per_1k_median=(
                "saves_per_1k",
                "median",
            ),
        )
    )

    return aggregated
