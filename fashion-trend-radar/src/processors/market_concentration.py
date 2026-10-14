"""
Market Entry Risk — separate from Fashion Score. Fashion Score answers
"is interest growing?"; this answers "can we enter profitably and
differentiated?". Needs seller/listing/price data per keyword (Amazon,
Google Shopping, AliExpress, Meta Ad Library) that this project does not
collect yet -- see TZ_trend_scoring.md steps 3-6. Every function here is
usable today only with manually-entered or externally-supplied rows.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return round(max(low, min(high, value)), 2)


def normalized_hhi(hhi: float) -> float:
    """Переводим HHI 0-10000 в 0-100."""
    return clamp((hhi / 10_000) * 100)


def calculate_hhi(
    df: pd.DataFrame,
    seller_col: str = "seller",
    weight_col: str = "proxy_sales"
) -> dict:
    """
    Рассчитывает HHI по наблюдаемому proxy weight.

    proxy_sales может быть:
    - estimated_monthly_sales;
    - число отзывов;
    - число заказов, если доступно;
    - visibility / rank score;
    - количество SKU с весом по rank.

    Нельзя смешивать разные типы веса внутри одного расчёта.
    """
    data = df[[seller_col, weight_col]].copy()

    data[weight_col] = pd.to_numeric(
        data[weight_col],
        errors="coerce"
    ).fillna(0)

    seller_weights = (
        data.groupby(seller_col)[weight_col]
        .sum()
        .sort_values(ascending=False)
    )

    total_weight = seller_weights.sum()

    if total_weight <= 0:
        return {
            "hhi": 0.0,
            "market_label": "NO_DATA",
            "seller_count": 0,
            "top_seller_share_pct": 0.0,
            "shares": pd.DataFrame(),
        }

    shares_pct = (seller_weights / total_weight) * 100
    hhi = float((shares_pct ** 2).sum())

    if hhi < 1500:
        label = "LOW_CONCENTRATION"
    elif hhi < 2500:
        label = "MODERATE_CONCENTRATION"
    else:
        label = "HIGH_CONCENTRATION"

    shares_df = (
        shares_pct
        .rename("share_pct")
        .reset_index()
        .sort_values("share_pct", ascending=False)
    )

    return {
        "hhi": round(hhi, 2),
        "market_label": label,
        "seller_count": int(len(shares_df)),
        "top_seller_share_pct": round(
            float(shares_df["share_pct"].iloc[0]),
            2,
        ),
        "shares": shares_df,
    }


def concentration_ratio(
    shares_df: pd.DataFrame,
    share_col: str = "share_pct",
    top_n: int = 5
) -> float:
    """Суммарная доля top-N sellers (CR3 при top_n=3, CR5 при top_n=5)."""
    return round(
        float(
            shares_df
            .sort_values(share_col, ascending=False)
            .head(top_n)[share_col]
            .sum()
        ),
        2
    )


def calculate_clone_saturation_index(
    image_duplicate_ratio: float,
    title_duplicate_ratio: float,
    seller_hhi: float,
    creative_similarity_ratio: float = 0.0
) -> dict:
    """
    Все ratio передавать в форме 0-1:
    0.42 = 42% товаров имеют одинаковые/почти одинаковые фото.
    """
    image_score = clamp(image_duplicate_ratio * 100)
    title_score = clamp(title_duplicate_ratio * 100)
    seller_score = normalized_hhi(seller_hhi)
    creative_score = clamp(creative_similarity_ratio * 100)

    csi = (
        image_score * 0.45
        + title_score * 0.30
        + seller_score * 0.15
        + creative_score * 0.10
    )

    csi = clamp(csi)

    if csi >= 70:
        label = "CLONE_HEAVY"
    elif csi >= 40:
        label = "MODERATE_CLONING"
    else:
        label = "DIFFERENTIABLE"

    return {
        "clone_saturation_index": csi,
        "label": label,
        "image_score": image_score,
        "title_score": title_score,
        "seller_concentration_score": seller_score,
        "creative_similarity_score": creative_score,
    }


def price_concentration_metrics(prices: list[float]) -> dict:
    series = pd.Series(prices, dtype=float).dropna()

    if len(series) < 3 or series.mean() <= 0:
        return {
            "price_mean": 0.0,
            "price_median": 0.0,
            "price_std": 0.0,
            "price_cv": 0.0,
            "label": "NOT_ENOUGH_DATA",
        }

    mean_price = float(series.mean())
    std_price = float(series.std(ddof=0))
    price_cv = std_price / mean_price

    if price_cv < 0.10:
        label = "TIGHT_PRICE_WAR_RISK"
    elif price_cv < 0.25:
        label = "MODERATE_PRICE_CLUSTERING"
    else:
        label = "BROAD_PRICE_POSITIONING"

    return {
        "price_mean": round(mean_price, 2),
        "price_median": round(float(series.median()), 2),
        "price_std": round(std_price, 2),
        "price_cv": round(price_cv, 3),
        "label": label,
    }


def calculate_market_entry_risk(
    clone_saturation_index: float,
    seller_hhi: float,
    price_cv: float,
    creative_similarity_ratio: float,
    supplier_count: int
) -> dict:
    brand_concentration = min(100, (seller_hhi / 10_000) * 100)

    # Чем меньше CV цены, тем выше риск ценовой войны.
    if price_cv <= 0.10:
        price_war_risk = 100
    elif price_cv >= 0.30:
        price_war_risk = 10
    else:
        price_war_risk = 100 - (((price_cv - 0.10) / 0.20) * 90)

    creative_risk = min(100, creative_similarity_ratio * 100)

    # Чем меньше поставщиков, тем выше supply risk.
    if supplier_count <= 1:
        supplier_risk = 100
    elif supplier_count == 2:
        supplier_risk = 65
    elif supplier_count <= 4:
        supplier_risk = 35
    else:
        supplier_risk = 10

    risk = (
        clone_saturation_index * 0.30
        + brand_concentration * 0.25
        + price_war_risk * 0.20
        + creative_risk * 0.15
        + supplier_risk * 0.10
    )

    if risk >= 70:
        label = "HIGH_ENTRY_RISK"
    elif risk >= 45:
        label = "MEDIUM_ENTRY_RISK"
    else:
        label = "LOW_ENTRY_RISK"

    return {
        "market_entry_risk": round(risk, 2),
        "label": label,
        "brand_concentration": round(brand_concentration, 2),
        "price_war_risk": round(price_war_risk, 2),
        "creative_risk": round(creative_risk, 2),
        "supplier_risk": supplier_risk,
    }


# ---------------------------------------------------------------------------
# Refined combined HHI + C4 + CR8 entry point (preferred over calculate_hhi +
# concentration_ratio above for new code -- single call, adds
# effective_competitors and a lower-cased/trimmed seller key so "Brand A" and
# "brand a " don't get counted as two different sellers).
# ---------------------------------------------------------------------------


@dataclass
class ConcentrationResult:
    hhi: float
    c4: float
    cr8: float
    seller_count: int
    top_seller_share: float
    effective_competitors: float
    label: str
    shares: pd.DataFrame


def calculate_market_concentration(
    df: pd.DataFrame,
    seller_col: str = "seller",
    weight_col: str = "proxy_sales"
) -> ConcentrationResult:
    """
    df: одна строка = товар, листинг или наблюдение конкурента.

    weight_col должен быть единым proxy во всём наборе:
    estimated_sales / revenue_estimate / review_count /
    visibility_score / rank_weight.
    """

    data = df[[seller_col, weight_col]].copy()

    data[seller_col] = (
        data[seller_col]
        .fillna("UNKNOWN")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    data[weight_col] = pd.to_numeric(
        data[weight_col],
        errors="coerce"
    ).fillna(0)

    data = data[data[weight_col] > 0]

    if data.empty:
        return ConcentrationResult(
            hhi=0.0,
            c4=0.0,
            cr8=0.0,
            seller_count=0,
            top_seller_share=0.0,
            effective_competitors=0.0,
            label="NO_DATA",
            shares=pd.DataFrame(
                columns=[seller_col, "weight", "share_pct"]
            ),
        )

    grouped = (
        data.groupby(seller_col, as_index=False)[weight_col]
        .sum()
        .rename(columns={weight_col: "weight"})
        .sort_values("weight", ascending=False)
        .reset_index(drop=True)
    )

    total_weight = grouped["weight"].sum()

    grouped["share_pct"] = (
        grouped["weight"] / total_weight * 100
    )

    hhi = float((grouped["share_pct"] ** 2).sum())

    c4 = float(grouped.head(4)["share_pct"].sum())
    cr8 = float(grouped.head(8)["share_pct"].sum())

    # Интуитивное дополнение к HHI:
    # например HHI = 2 500 -> около 4 "равных" игроков.
    effective_competitors = 10_000 / hhi if hhi > 0 else 0

    if hhi < 1500:
        label = "LOW_CONCENTRATION"
    elif hhi < 2500:
        label = "MODERATE_CONCENTRATION"
    else:
        label = "HIGH_CONCENTRATION"

    return ConcentrationResult(
        hhi=round(hhi, 2),
        c4=round(c4, 2),
        cr8=round(cr8, 2),
        seller_count=int(len(grouped)),
        top_seller_share=round(float(grouped.iloc[0]["share_pct"]), 2),
        effective_competitors=round(effective_competitors, 2),
        label=label,
        shares=grouped,
    )
