from __future__ import annotations

from dataclasses import dataclass
import math


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, value)), 2)


def scale_log(
    value: float,
    min_value: float,
    max_value: float
) -> float:
    """
    Логарифмическая шкала:
    10 -> 100 листингов важно,
    1 000 -> 10 000 листингов уже не должно ломать расчёт.
    """
    value = max(float(value), 0)
    min_value = max(float(min_value), 0)
    max_value = max(float(max_value), min_value + 1)

    numerator = math.log1p(value) - math.log1p(min_value)
    denominator = math.log1p(max_value) - math.log1p(min_value)

    return clamp((numerator / denominator) * 100)


def scale_linear(
    value: float,
    min_value: float,
    max_value: float
) -> float:
    if max_value <= min_value:
        return 0.0

    return clamp(
        ((value - min_value) / (max_value - min_value)) * 100
    )


@dataclass
class SaturationInput:
    keyword: str

    # Маркетплейсы и Google Shopping.
    duplicate_listing_count: int = 0
    unique_seller_count: int = 0
    image_duplicate_ratio: float = 0.0
    exact_title_ratio: float = 0.0

    # Meta Ads.
    meta_active_ads: int = 0
    meta_unique_advertisers: int = 0
    meta_oldest_ad_days: int = 0
    ad_creative_similarity: float = 0.0

    # Возможность отличиться.
    supplier_count: int = 0
    differentiation_options: int = 0
    has_clear_niche: bool = False


def calculate_saturation_penalty(data: SaturationInput) -> dict:
    """
    Возвращает штраф 0–15.

    0 = свободнее/можно отличиться.
    15 = рынок переполнен клонами,
         войти без сильного УТП опасно.
    """

    # 1. Дубликаты товара — главный риск для дропшиппинга.
    duplicate_score = scale_log(
        data.duplicate_listing_count,
        min_value=10,
        max_value=1500
    )

    # 2. Продавцы: много продавцов = больше ценовой конкуренции.
    seller_score = scale_log(
        data.unique_seller_count,
        min_value=3,
        max_value=300
    )

    # 3. Доля одинаковых фото и почти идентичных titles.
    image_score = clamp(data.image_duplicate_ratio * 100)
    title_score = clamp(data.exact_title_ratio * 100)

    # 4. Конкуренция рекламой.
    # Meta ads сами по себе не всегда плохой сигнал:
    # старые объявления говорят, что категория может продаваться.
    ads_volume_score = scale_log(
        data.meta_active_ads,
        min_value=3,
        max_value=250
    )

    advertiser_score = scale_log(
        data.meta_unique_advertisers,
        min_value=2,
        max_value=100
    )

    creative_clone_score = clamp(data.ad_creative_similarity * 100)

    # 5. Возможность отличиться — уменьшает штраф.
    supplier_relief = scale_linear(
        data.supplier_count,
        min_value=1,
        max_value=8
    )

    differentiation_relief = scale_linear(
        data.differentiation_options,
        min_value=0,
        max_value=8
    )

    niche_relief = 100.0 if data.has_clear_niche else 0.0

    saturation_raw = (
        duplicate_score * 0.25
        + seller_score * 0.10
        + image_score * 0.20
        + title_score * 0.10
        + ads_volume_score * 0.10
        + advertiser_score * 0.05
        + creative_clone_score * 0.10
        - supplier_relief * 0.04
        - differentiation_relief * 0.04
        - niche_relief * 0.02
    )

    saturation_raw = clamp(saturation_raw)

    # Конвертация 0–100 в штраф 0–15.
    penalty = round((saturation_raw / 100) * 15, 2)

    if penalty >= 11:
        label = "HIGH_SATURATION"
    elif penalty >= 6:
        label = "MEDIUM_SATURATION"
    else:
        label = "LOW_SATURATION"

    return {
        "keyword": data.keyword,
        "saturation_raw": saturation_raw,
        "saturation_penalty": penalty,
        "saturation_label": label,

        "duplicate_score": duplicate_score,
        "seller_score": seller_score,
        "image_score": image_score,
        "title_score": title_score,
        "ads_volume_score": ads_volume_score,
        "advertiser_score": advertiser_score,
        "creative_clone_score": creative_clone_score,

        "supplier_relief": supplier_relief,
        "differentiation_relief": differentiation_relief,
        "niche_relief": niche_relief,
    }
