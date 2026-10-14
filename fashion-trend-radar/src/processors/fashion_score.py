from __future__ import annotations

from dataclasses import dataclass, asdict
import math


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, value)), 2)


def scale_linear(
    value: float,
    min_value: float,
    max_value: float
) -> float:
    if max_value <= min_value:
        return 0.0

    scaled = (value - min_value) / (max_value - min_value)
    return clamp(scaled * 100)


def scale_log(
    value: float,
    min_value: float,
    max_value: float
) -> float:
    value = max(float(value), 0)
    min_value = max(float(min_value), 0)
    max_value = max(float(max_value), min_value + 1)

    numerator = math.log1p(value) - math.log1p(min_value)
    denominator = math.log1p(max_value) - math.log1p(min_value)

    return clamp((numerator / denominator) * 100)


def weighted_average(parts: list[tuple[float, float]]) -> float:
    """
    parts = [(score_0_100, weight), ...]
    """
    total_weight = sum(weight for _, weight in parts)

    if total_weight == 0:
        return 0.0

    result = sum(score * weight for score, weight in parts) / total_weight
    return clamp(result)


@dataclass
class FashionCandidate:
    keyword: str

    # Google Trends.
    google_growth_7d: float = 0.0
    google_growth_30d: float = 0.0
    google_growth_90d: float = 0.0
    google_recent_interest: float = 0.0
    google_rising_queries_count: int = 0

    # Pinterest.
    pinterest_weekly_growth: float = 0.0
    pinterest_monthly_growth: float = 0.0
    pinterest_yearly_growth: float = 0.0
    pinterest_related_keywords_count: int = 0

    # TikTok за последние 30 дней.
    tiktok_video_count: int = 0
    tiktok_unique_creators: int = 0
    tiktok_views_median: float = 0.0
    tiktok_engagement_rate: float = 0.0
    tiktok_shares_per_1k_views: float = 0.0
    tiktok_saves_per_1k_views: float = 0.0
    tiktok_buy_intent_comments: int = 0

    # Коммерческая валидация.
    meta_active_ads: int = 0
    meta_oldest_ad_days: int = 0
    meta_unique_advertisers: int = 0
    amazon_rank_change_pct: float = 0.0
    retailer_confirmation_count: int = 0

    # Уникальность и контент.
    unique_product_angle: bool = False
    content_angles_count: int = 0
    supplier_count: int = 0
    duplicate_listing_count: int = 0

    # Деньги.
    sell_price: float = 0.0
    product_cost: float = 0.0
    shipping_cost: float = 0.0
    payment_fee_pct: float = 0.03
    return_reserve_pct: float = 0.12


def google_score(c: FashionCandidate) -> float:
    growth_7d = scale_linear(c.google_growth_7d, -10, 80)
    growth_30d = scale_linear(c.google_growth_30d, -10, 120)
    growth_90d = scale_linear(c.google_growth_90d, -10, 160)

    interest = scale_linear(c.google_recent_interest, 10, 75)
    rising_queries = scale_linear(c.google_rising_queries_count, 0, 10)

    return weighted_average([
        (growth_7d, 0.15),
        (growth_30d, 0.35),
        (growth_90d, 0.25),
        (interest, 0.10),
        (rising_queries, 0.15),
    ])


def pinterest_score(c: FashionCandidate) -> float:
    weekly = scale_linear(c.pinterest_weekly_growth, -10, 60)
    monthly = scale_linear(c.pinterest_monthly_growth, -10, 100)
    yearly = scale_linear(c.pinterest_yearly_growth, -20, 120)
    related = scale_linear(c.pinterest_related_keywords_count, 0, 15)

    return weighted_average([
        (weekly, 0.35),
        (monthly, 0.35),
        (yearly, 0.15),
        (related, 0.15),
    ])


def tiktok_score(c: FashionCandidate) -> float:
    video_count = scale_log(c.tiktok_video_count, 2, 80)
    creators = scale_log(c.tiktok_unique_creators, 2, 30)
    median_views = scale_log(c.tiktok_views_median, 1_000, 500_000)

    engagement = scale_linear(
        c.tiktok_engagement_rate * 100,
        2,
        15
    )

    shares = scale_linear(c.tiktok_shares_per_1k_views, 0.5, 20)
    saves = scale_linear(c.tiktok_saves_per_1k_views, 0.5, 25)
    buy_intent = scale_log(c.tiktok_buy_intent_comments, 1, 100)

    return weighted_average([
        (video_count, 0.15),
        (creators, 0.20),
        (median_views, 0.15),
        (engagement, 0.10),
        (shares, 0.12),
        (saves, 0.13),
        (buy_intent, 0.15),
    ])


def commercial_score(c: FashionCandidate) -> float:
    active_ads = scale_log(c.meta_active_ads, 0, 50)
    ad_longevity = scale_linear(c.meta_oldest_ad_days, 0, 60)
    advertisers = scale_log(c.meta_unique_advertisers, 0, 20)

    rank_change = scale_linear(
        c.amazon_rank_change_pct,
        -10,
        80
    )

    retailers = scale_linear(c.retailer_confirmation_count, 0, 6)

    return weighted_average([
        (active_ads, 0.15),
        (ad_longevity, 0.35),
        (advertisers, 0.15),
        (rank_change, 0.15),
        (retailers, 0.20),
    ])


def uniqueness_score(c: FashionCandidate) -> float:
    product_angle = 100 if c.unique_product_angle else 25
    content = scale_linear(c.content_angles_count, 0, 25)

    # Меньше одинаковых листингов = выше шанс сделать отличимый оффер.
    duplicate_penalty = scale_log(c.duplicate_listing_count, 0, 500)
    low_saturation = 100 - duplicate_penalty

    return weighted_average([
        (product_angle, 0.40),
        (content, 0.30),
        (low_saturation, 0.30),
    ])


def margin_score(c: FashionCandidate) -> tuple[float, float]:
    """
    Возвращает:
    1. Score 0–100.
    2. Contribution margin до расходов на рекламу.
    """
    if c.sell_price <= 0:
        return 0.0, 0.0

    payment_fee = c.sell_price * c.payment_fee_pct
    return_reserve = c.sell_price * c.return_reserve_pct

    contribution_profit = (
        c.sell_price
        - c.product_cost
        - c.shipping_cost
        - payment_fee
        - return_reserve
    )

    contribution_margin_pct = (
        contribution_profit / c.sell_price
    ) * 100

    supplier_score = scale_linear(c.supplier_count, 1, 6)
    margin_component = scale_linear(contribution_margin_pct, 15, 60)

    score = weighted_average([
        (margin_component, 0.75),
        (supplier_score, 0.25),
    ])

    return score, round(contribution_margin_pct, 2)


def classify_score(score: float) -> str:
    if score >= 75:
        return "TEST_NOW"
    if score >= 55:
        return "WATCHLIST"
    if score >= 35:
        return "WEAK"
    return "REJECT"


def calculate_fashion_score(
    c: FashionCandidate,
    seasonality_penalty: float,
    saturation_penalty: float,
) -> dict:
    """
    seasonality_penalty / saturation_penalty: already-computed 0-15 values
    from src.processors.seasonality.detect_seasonality(...).penalty and
    src.processors.saturation.calculate_saturation_penalty(...)["saturation_penalty"].
    Computed here directly (not re-derived from `c`) so they are never
    subtracted twice -- see TZ_trend_scoring.md.
    """
    g_score = google_score(c)
    p_score = pinterest_score(c)
    t_score = tiktok_score(c)
    c_score = commercial_score(c)
    u_score = uniqueness_score(c)
    m_score, contribution_margin_pct = margin_score(c)

    base_score = (
        g_score * 0.25
        + p_score * 0.18
        + t_score * 0.20
        + c_score * 0.15
        + u_score * 0.12
        + m_score * 0.10
    )

    fashion_score = clamp(base_score - seasonality_penalty - saturation_penalty)

    return {
        "keyword": c.keyword,
        "fashion_score": fashion_score,
        "status": classify_score(fashion_score),

        "google_score": round(g_score, 2),
        "pinterest_score": round(p_score, 2),
        "tiktok_score": round(t_score, 2),
        "commercial_score": round(c_score, 2),
        "uniqueness_score": round(u_score, 2),
        "margin_score": round(m_score, 2),

        "seasonality_penalty": seasonality_penalty,
        "saturation_penalty": saturation_penalty,
        "contribution_margin_pct": contribution_margin_pct,
    }
