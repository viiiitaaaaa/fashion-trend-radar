"""
Richer seasonality analysis than seasonality.py's detect_seasonality():
adds a full seasonal-index-by-week-of-year table and a seasonality_strength
figure, not just the year-over-year penalty. Needs the same >=80 weeks of
history seasonality.py needs -- with only the current ~53-week Bright Data
series it also returns NOT_ENOUGH_HISTORY. Once 2 years of history
accumulate via src/collectors/google_trends_cached.py, prefer this
module for its per-week seasonal_index; detect_seasonality() in
seasonality.py stays as the lighter-weight version already wired into
run_fashion_score.py.
"""

from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass
class SeasonalityAnalysis:
    keyword: str
    recent_4w_avg: float
    previous_4w_avg: float
    same_4w_last_year_avg: float
    trailing_52w_avg: float
    growth_4w_pct: float
    yoy_growth_4w_pct: float
    growth_vs_baseline_pct: float
    seasonal_index_current: float
    seasonality_strength: float
    peak_week: int | None
    label: str
    penalty: float
    seasonal_index: pd.DataFrame


def safe_pct_change(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0

    return round(
        ((current - previous) / previous) * 100,
        2,
    )


def prepare_weekly_data(
    df: pd.DataFrame,
    date_col: str = "date",
    value_col: str = "interest"
) -> pd.DataFrame:
    data = df.copy()

    data[date_col] = pd.to_datetime(data[date_col])
    data[value_col] = pd.to_numeric(
        data[value_col],
        errors="coerce",
    ).fillna(0)

    if "is_partial" in data.columns:
        data = data[~data["is_partial"].astype(bool)]

    weekly = (
        data
        .set_index(date_col)[value_col]
        .resample("W-SUN")
        .mean()
        .fillna(0)
        .rename("interest")
        .to_frame()
    )

    weekly["week_of_year"] = (
        weekly.index.isocalendar().week.astype(int)
    )

    return weekly


def analyze_seasonality(
    df: pd.DataFrame,
    keyword: str,
    date_col: str = "date",
    value_col: str = "interest"
) -> SeasonalityAnalysis:
    weekly = prepare_weekly_data(
        df=df,
        date_col=date_col,
        value_col=value_col,
    )

    if len(weekly) < 80:
        return SeasonalityAnalysis(
            keyword=keyword,
            recent_4w_avg=0.0,
            previous_4w_avg=0.0,
            same_4w_last_year_avg=0.0,
            trailing_52w_avg=0.0,
            growth_4w_pct=0.0,
            yoy_growth_4w_pct=0.0,
            growth_vs_baseline_pct=0.0,
            seasonal_index_current=1.0,
            seasonality_strength=0.0,
            peak_week=None,
            label="NOT_ENOUGH_HISTORY",
            penalty=0.0,
            seasonal_index=pd.DataFrame(),
        )

    recent_4w = weekly["interest"].iloc[-4:].mean()
    previous_4w = weekly["interest"].iloc[-8:-4].mean()
    same_4w_last_year = weekly["interest"].iloc[-56:-52].mean()
    trailing_52w = weekly["interest"].iloc[-52:].mean()

    growth_4w = safe_pct_change(
        recent_4w,
        previous_4w,
    )

    yoy_growth = safe_pct_change(
        recent_4w,
        same_4w_last_year,
    )

    growth_vs_baseline = safe_pct_change(
        recent_4w,
        trailing_52w,
    )

    overall_mean = weekly["interest"].mean()

    seasonal_index = (
        weekly
        .groupby("week_of_year", as_index=False)["interest"]
        .mean()
        .rename(columns={"interest": "week_mean"})
    )

    seasonal_index["seasonal_index"] = (
        seasonal_index["week_mean"]
        / max(overall_mean, 0.01)
    )

    current_week = int(weekly.index[-1].isocalendar().week)

    current_seasonal_index = float(
        seasonal_index
        .loc[
            seasonal_index["week_of_year"] == current_week,
            "seasonal_index"
        ]
        .iloc[0]
    )

    seasonality_strength = float(
        seasonal_index["seasonal_index"].std(ddof=0)
        / max(
            seasonal_index["seasonal_index"].mean(),
            0.01,
        )
    )

    peak_week = int(
        seasonal_index.loc[
            seasonal_index["seasonal_index"].idxmax(),
            "week_of_year"
        ]
    )

    # Значение 0-15: штраф к Fashion Score.
    penalty = 0.0
    label = "NEUTRAL"

    # Текущий период традиционно сезонно сильный,
    # но YoY почти не растёт: это не новая волна.
    if (
        current_seasonal_index >= 1.40
        and yoy_growth <= 15
        and growth_vs_baseline >= 20
    ):
        penalty = 15.0
        label = "RECURRING_SEASONAL_PEAK"

    # Есть заметная сезонность и текущий рост,
    # но нового YoY acceleration нет.
    elif (
        seasonality_strength >= 0.35
        and current_seasonal_index >= 1.20
        and yoy_growth < 25
    ):
        penalty = 9.0
        label = "LIKELY_SEASONAL"

    # Рост против прошлого года сильнее сезонного эффекта.
    elif yoy_growth >= 35 and growth_4w >= 15:
        penalty = 0.0
        label = "FRESH_ACCELERATION"

    # Ранний рост: пока недостаточно доказательств.
    elif growth_4w >= 15:
        penalty = 3.0
        label = "EARLY_UPTREND"

    return SeasonalityAnalysis(
        keyword=keyword,
        recent_4w_avg=round(recent_4w, 2),
        previous_4w_avg=round(previous_4w, 2),
        same_4w_last_year_avg=round(
            same_4w_last_year,
            2,
        ),
        trailing_52w_avg=round(trailing_52w, 2),
        growth_4w_pct=growth_4w,
        yoy_growth_4w_pct=yoy_growth,
        growth_vs_baseline_pct=growth_vs_baseline,
        seasonal_index_current=round(
            current_seasonal_index,
            3,
        ),
        seasonality_strength=round(
            seasonality_strength,
            3,
        ),
        peak_week=peak_week,
        label=label,
        penalty=penalty,
        seasonal_index=seasonal_index,
    )


# ---------------------------------------------------------------------------
# Seasonal-adjusted momentum: divides out the seasonal_index so a spike that
# looks big only because it's the usual seasonal week reads flat once
# adjusted. Complements analyze_seasonality() above (which gives a single
# 0-15 penalty) with a full weekly series for charting/inspection.
# ---------------------------------------------------------------------------

import numpy as np


def decompose_fashion_seasonality(
    weekly: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    weekly: output of prepare_weekly_data() above (needs 'interest' and
    'week_of_year' columns).

    Возвращает:
    1. weekly data с seasonal index и seasonal-adjusted interest.
    2. таблицу season profile по неделям года.
    """
    data = weekly.reset_index().copy()

    baseline = data["interest"].mean()

    season_profile = (
        data
        .groupby("week_of_year", as_index=False)["interest"]
        .mean()
        .rename(columns={"interest": "seasonal_mean"})
    )

    season_profile["seasonal_index"] = (
        season_profile["seasonal_mean"] / max(baseline, 0.01)
    )

    data = data.merge(
        season_profile[["week_of_year", "seasonal_index"]],
        on="week_of_year",
        how="left",
    )

    # Если индекс сезона > 1, спрос в эту неделю обычно выше.
    # Делим на index, чтобы видеть спрос "с поправкой на сезон".
    data["seasonally_adjusted_interest"] = (
        data["interest"] / data["seasonal_index"].clip(lower=0.01)
    )

    data["trend_4w_ma"] = (
        data["seasonally_adjusted_interest"].rolling(window=4, min_periods=2).mean()
    )

    data["trend_12w_ma"] = (
        data["seasonally_adjusted_interest"].rolling(window=12, min_periods=4).mean()
    )

    data["seasonally_adjusted_momentum_pct"] = (
        data["trend_4w_ma"]
        .pct_change(periods=4)
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0)
        * 100
    )

    return data, season_profile


# ---------------------------------------------------------------------------
# STL decomposition (statsmodels) -- a third, statistically rigorous take on
# seasonality vs. detect_seasonality() (seasonality.py, lightweight, already
# wired) and decompose_fashion_seasonality() (above, simpler seasonal index).
# Needs >=104 weekly points same as the others; with STL that's the hard
# statsmodels requirement (period*2), not just an honesty convention.
# Exploratory signal only until 3+ years of history exist.
# ---------------------------------------------------------------------------

from statsmodels.tsa.seasonal import STL


def prepare_weekly_series(
    df: pd.DataFrame,
    date_col: str = "date",
    value_col: str = "interest",
) -> pd.Series:
    data = df.copy()

    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce").fillna(0)

    if "is_partial" in data.columns:
        data = data[~data["is_partial"].astype(bool)].copy()

    series = (
        data
        .dropna(subset=[date_col])
        .set_index(date_col)[value_col]
        .sort_index()
        .resample("W-SUN")
        .mean()
        .fillna(0)
    )

    series = series.asfreq("W-SUN", fill_value=0)

    return series


def stl_decompose_weekly(
    weekly_series: pd.Series,
    period: int = 52,
) -> pd.DataFrame:
    """Требует минимум 2 полных сезонных цикла (104 недели для period=52)."""
    if len(weekly_series) < period * 2:
        raise ValueError(f"Need at least {period * 2} weekly observations.")

    # `seasonal` обязательно нечётный и >= 7. 13 даёт достаточно плавную
    # сезонную компоненту для fashion research.
    model = STL(weekly_series, period=period, seasonal=13, robust=True)
    result = model.fit()

    decomposed = pd.DataFrame({
        "interest": weekly_series,
        "trend": result.trend,
        "seasonal": result.seasonal,
        "residual": result.resid,
    })

    decomposed["seasonally_adjusted"] = decomposed["interest"] - decomposed["seasonal"]

    decomposed["trend_momentum_4w_pct"] = (
        decomposed["trend"]
        .pct_change(4)
        .replace([float("inf"), float("-inf")], 0)
        .fillna(0)
        * 100
    )

    residual_std = decomposed["residual"].std(ddof=0)

    decomposed["residual_z"] = decomposed["residual"] / max(residual_std, 0.01)
    decomposed["anomaly"] = decomposed["residual_z"].abs() >= 2.5

    return decomposed
