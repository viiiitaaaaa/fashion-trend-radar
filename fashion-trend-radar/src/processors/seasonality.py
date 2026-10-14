from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass
class SeasonalityResult:
    penalty: float
    label: str
    recent_4w_avg: float
    previous_4w_avg: float
    same_period_last_year_avg: float
    trailing_52w_avg: float
    growth_vs_previous_4w_pct: float
    growth_vs_last_year_pct: float
    growth_vs_baseline_pct: float
    peak_month: int | None
    peak_alignment: bool


def safe_pct_change(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0
    return round(((current - previous) / previous) * 100, 2)


def prepare_weekly_series(
    df: pd.DataFrame,
    date_col: str = "date",
    value_col: str = "interest"
) -> pd.DataFrame:
    """
    Вход:
        date, interest

    Выход:
        непрерывный еженедельный ряд.
    """
    data = df[[date_col, value_col]].copy()
    data[date_col] = pd.to_datetime(data[date_col])
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce").fillna(0)

    data = data.set_index(date_col).sort_index()
    weekly = data.resample("W-SUN")[value_col].mean().fillna(0)

    return weekly.to_frame(name="interest")


def detect_seasonality(
    df: pd.DataFrame,
    date_col: str = "date",
    value_col: str = "interest"
) -> SeasonalityResult:
    weekly_df = prepare_weekly_series(df, date_col, value_col)
    values = weekly_df["interest"]

    if len(values) < 80:
        return SeasonalityResult(
            penalty=0.0,
            label="NOT_ENOUGH_HISTORY",
            recent_4w_avg=0.0,
            previous_4w_avg=0.0,
            same_period_last_year_avg=0.0,
            trailing_52w_avg=0.0,
            growth_vs_previous_4w_pct=0.0,
            growth_vs_last_year_pct=0.0,
            growth_vs_baseline_pct=0.0,
            peak_month=None,
            peak_alignment=False,
        )

    recent_4w = values.iloc[-4:].mean()
    previous_4w = values.iloc[-8:-4].mean()

    # 52 недели назад: берём такой же 4-недельный отрезок.
    same_period_last_year = values.iloc[-56:-52].mean()

    trailing_52w = values.iloc[-52:].mean()

    growth_vs_previous = safe_pct_change(recent_4w, previous_4w)
    growth_vs_last_year = safe_pct_change(
        recent_4w,
        same_period_last_year
    )
    growth_vs_baseline = safe_pct_change(
        recent_4w,
        trailing_52w
    )

    last_52 = weekly_df.iloc[-52:].copy()
    previous_52 = weekly_df.iloc[-104:-52].copy()

    current_peak_month = int(last_52["interest"].idxmax().month)
    previous_peak_month = int(previous_52["interest"].idxmax().month)

    peak_alignment = current_peak_month == previous_peak_month

    # Штраф 0–15.
    penalty = 0.0
    label = "FRESH_OR_NEUTRAL"

    # Сценарий 1:
    # Сейчас есть высокий спрос относительно среднего,
    # но уровень почти такой же, как в тот же сезон год назад.
    if (
        growth_vs_baseline >= 30
        and abs(growth_vs_last_year) <= 15
        and peak_alignment
    ):
        penalty = 15.0
        label = "RECURRING_SEASONAL_PEAK"

    # Сценарий 2:
    # Подъём похож на сезонный, но повтор не настолько чистый.
    elif (
        growth_vs_baseline >= 20
        and growth_vs_last_year < 20
    ):
        penalty = 9.0
        label = "LIKELY_SEASONAL"

    # Сценарий 3:
    # Растёт быстрее прошлого года —
    # сезонность есть, но это уже новая волна.
    elif (
        growth_vs_previous >= 20
        and growth_vs_last_year >= 35
    ):
        penalty = 0.0
        label = "FRESH_ACCELERATION"

    # Сценарий 4:
    # Спрос растёт, но данных недостаточно для уверенного вывода.
    elif growth_vs_previous >= 15:
        penalty = 3.0
        label = "EARLY_UPTREND"

    return SeasonalityResult(
        penalty=penalty,
        label=label,
        recent_4w_avg=round(recent_4w, 2),
        previous_4w_avg=round(previous_4w, 2),
        same_period_last_year_avg=round(same_period_last_year, 2),
        trailing_52w_avg=round(trailing_52w, 2),
        growth_vs_previous_4w_pct=growth_vs_previous,
        growth_vs_last_year_pct=growth_vs_last_year,
        growth_vs_baseline_pct=growth_vs_baseline,
        peak_month=current_peak_month,
        peak_alignment=peak_alignment,
    )


def build_seasonal_index(
    df: pd.DataFrame,
    date_col: str = "date",
    value_col: str = "interest"
) -> pd.DataFrame:
    """Seasonal index per ISO week, once 2-3 years of history exist.
    Not required for the current penalty logic (detect_seasonality's
    year-over-year comparison already catches most dangerous seasonality)."""
    data = df[[date_col, value_col]].copy()
    data[date_col] = pd.to_datetime(data[date_col])
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce").fillna(0)

    data["week_of_year"] = data[date_col].dt.isocalendar().week.astype(int)

    overall_mean = data[value_col].mean()

    seasonal = (
        data.groupby("week_of_year")[value_col]
        .mean()
        .reset_index(name="week_mean")
    )

    seasonal["seasonal_index"] = (
        seasonal["week_mean"] / max(overall_mean, 0.01)
    )

    return seasonal
