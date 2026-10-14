"""
Provider-agnostic marketplace data shape. Plug in an authorized source
(official Seller API, permitted analytics service, CSV export) behind
MarketplaceProvider -- nothing downstream cares which one. Deliberately
does NOT include a scraper for Wildberries/Ozon or any other marketplace's
public search/listing pages: that would mean bypassing anti-bot protection,
which is out of scope. Your own store's data goes through the official
Seller API; competitor visibility goes through a permitted data provider,
not through evading defenses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import pandas as pd


@dataclass
class MarketplaceProduct:
    marketplace: str
    keyword: str
    product_id: str
    title: str
    brand: str | None
    seller: str | None
    price: float | None
    old_price: float | None
    rating: float | None
    review_count: int | None
    rank: int | None
    product_url: str | None
    image_url: str | None
    collected_at: str


class MarketplaceProvider(Protocol):
    def search_products(
        self,
        keyword: str,
        limit: int = 100
    ) -> list[MarketplaceProduct]:
        ...


def collect_marketplace_keywords(
    provider: MarketplaceProvider,
    keywords: list[str],
    limit_per_keyword: int = 100
) -> pd.DataFrame:
    rows = []

    for keyword in keywords:
        products = provider.search_products(
            keyword=keyword,
            limit=limit_per_keyword,
        )

        for product in products:
            rows.append(product.__dict__)

    return pd.DataFrame(rows)
