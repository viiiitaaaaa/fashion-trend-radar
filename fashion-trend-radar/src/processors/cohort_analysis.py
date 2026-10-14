"""
Cohort analysis -- independent of trend scoring, needs real Shopify order
history to mean anything. Useless before the first ~50-100 orders exist;
see TZ_trend_scoring.md for when to turn this on.
"""

from __future__ import annotations

import pandas as pd


def build_retention_cohorts(
    orders: pd.DataFrame,
    customer_col: str = "customer_id",
    date_col: str = "order_date"
) -> pd.DataFrame:
    data = orders.copy()

    data[date_col] = pd.to_datetime(data[date_col])

    data["order_month"] = (
        data[date_col]
        .dt.to_period("M")
    )

    first_orders = (
        data
        .groupby(customer_col)["order_month"]
        .min()
        .rename("cohort_month")
    )

    data = data.join(
        first_orders,
        on=customer_col,
    )

    data["cohort_index"] = (
        (data["order_month"].dt.year - data["cohort_month"].dt.year) * 12
        + data["order_month"].dt.month
        - data["cohort_month"].dt.month
    )

    cohort_counts = (
        data
        .groupby(["cohort_month", "cohort_index"])[customer_col]
        .nunique()
        .reset_index(name="customers")
    )

    cohort_size = (
        cohort_counts[
            cohort_counts["cohort_index"] == 0
        ][["cohort_month", "customers"]]
        .rename(columns={"customers": "cohort_size"})
    )

    cohort_counts = cohort_counts.merge(
        cohort_size,
        on="cohort_month",
        how="left",
    )

    cohort_counts["retention_rate"] = (
        cohort_counts["customers"]
        / cohort_counts["cohort_size"]
    )

    retention_matrix = cohort_counts.pivot(
        index="cohort_month",
        columns="cohort_index",
        values="retention_rate",
    )

    return retention_matrix.round(3)


def build_ltv_cohorts(
    orders: pd.DataFrame,
    customer_col: str = "customer_id",
    date_col: str = "order_date"
) -> pd.DataFrame:
    data = orders.copy()

    data[date_col] = pd.to_datetime(data[date_col])

    for col in [
        "revenue",
        "cogs",
        "shipping_cost",
        "payment_fee",
        "refund_amount",
    ]:
        data[col] = pd.to_numeric(
            data[col],
            errors="coerce"
        ).fillna(0)

    data["contribution_profit"] = (
        data["revenue"]
        - data["cogs"]
        - data["shipping_cost"]
        - data["payment_fee"]
        - data["refund_amount"]
    )

    data["order_month"] = data[date_col].dt.to_period("M")

    first_orders = (
        data
        .groupby(customer_col)["order_month"]
        .min()
        .rename("cohort_month")
    )

    data = data.join(
        first_orders,
        on=customer_col,
    )

    data["cohort_index"] = (
        (data["order_month"].dt.year - data["cohort_month"].dt.year) * 12
        + data["order_month"].dt.month
        - data["cohort_month"].dt.month
    )

    monthly_profit = (
        data
        .groupby(["cohort_month", "cohort_index"], as_index=False)
        .agg(
            contribution_profit=(
                "contribution_profit",
                "sum",
            ),
            customers=(customer_col, "nunique"),
        )
    )

    cohort_size = (
        data
        .groupby("cohort_month")[customer_col]
        .nunique()
        .rename("cohort_size")
    )

    monthly_profit = monthly_profit.join(
        cohort_size,
        on="cohort_month",
    )

    monthly_profit["ltv_per_original_customer"] = (
        monthly_profit["contribution_profit"]
        / monthly_profit["cohort_size"]
    )

    ltv_matrix = monthly_profit.pivot(
        index="cohort_month",
        columns="cohort_index",
        values="ltv_per_original_customer",
    )

    # Кумулятивный LTV: Month 0 + Month 1 + Month 2 ...
    return ltv_matrix.cumsum(axis=1).round(2)


def refund_metrics_by_segment(
    orders: pd.DataFrame,
    segment_col: str
) -> pd.DataFrame:
    data = orders.copy()

    for col in ["revenue", "refund_amount"]:
        data[col] = pd.to_numeric(
            data[col],
            errors="coerce"
        ).fillna(0)

    result = (
        data
        .groupby(segment_col, as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            gross_revenue=("revenue", "sum"),
            refunds=("refund_amount", "sum"),
            customers=("customer_id", "nunique"),
        )
    )

    result["refund_rate"] = (
        result["refunds"]
        / result["gross_revenue"].clip(lower=1)
    ).round(3)

    return result.sort_values(
        "refund_rate",
        ascending=False,
    )


# ---------------------------------------------------------------------------
# Refined cohort helpers matching Shopify's own cohort-report definition
# (group by first-order month, retention = active / cohort_size). Prefer
# these for new work; build_retention_cohorts()/build_ltv_cohorts() above
# still work standalone without running prepare_order_economics() first.
# build_cohort_ltv_matrix needs "contribution_profit" -- run
# src.processors.unit_economics.prepare_order_economics() on orders first.
# ---------------------------------------------------------------------------


def add_cohort_fields(
    orders: pd.DataFrame,
    customer_col: str = "customer_id",
    date_col: str = "order_date",
) -> pd.DataFrame:
    data = orders.copy()

    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data = data.dropna(subset=[customer_col, date_col])

    data["order_month"] = data[date_col].dt.to_period("M")

    first_order_month = (
        data.groupby(customer_col)["order_month"].min().rename("cohort_month")
    )

    data = data.join(first_order_month, on=customer_col)

    data["cohort_index"] = (
        (data["order_month"].dt.year - data["cohort_month"].dt.year) * 12
        + data["order_month"].dt.month
        - data["cohort_month"].dt.month
    )

    return data


def build_retention_matrix(
    cohort_orders: pd.DataFrame,
    customer_col: str = "customer_id",
) -> pd.DataFrame:
    """cohort_orders: output of add_cohort_fields()."""
    activity = (
        cohort_orders
        .groupby(["cohort_month", "cohort_index"], as_index=False)[customer_col]
        .nunique()
        .rename(columns={customer_col: "active_customers"})
    )

    cohort_sizes = (
        activity[activity["cohort_index"] == 0][["cohort_month", "active_customers"]]
        .rename(columns={"active_customers": "cohort_size"})
    )

    activity = activity.merge(cohort_sizes, on="cohort_month", how="left")

    activity["retention_pct"] = (
        activity["active_customers"] / activity["cohort_size"].clip(lower=1) * 100
    )

    matrix = activity.pivot(
        index="cohort_month", columns="cohort_index", values="retention_pct",
    )

    return matrix.round(1)


def build_cohort_ltv_matrix(
    cohort_orders: pd.DataFrame,
    customer_col: str = "customer_id",
) -> pd.DataFrame:
    """cohort_orders: add_cohort_fields() output, already run through
    unit_economics.prepare_order_economics() (needs contribution_profit)."""
    data = cohort_orders.copy()

    if "contribution_profit" not in data.columns:
        raise ValueError(
            "Run unit_economics.prepare_order_economics() before this."
        )

    monthly_profit = (
        data
        .groupby(["cohort_month", "cohort_index"], as_index=False)
        .agg(contribution_profit=("contribution_profit", "sum"))
    )

    cohort_sizes = (
        data.groupby("cohort_month")[customer_col].nunique().rename("cohort_size")
    )

    monthly_profit = monthly_profit.join(cohort_sizes, on="cohort_month")

    monthly_profit["profit_ltv_per_customer"] = (
        monthly_profit["contribution_profit"] / monthly_profit["cohort_size"].clip(lower=1)
    )

    ltv_matrix = monthly_profit.pivot(
        index="cohort_month", columns="cohort_index", values="profit_ltv_per_customer",
    )

    # В Month 2 -- суммарный LTV за Month 0 + 1 + 2.
    return ltv_matrix.cumsum(axis=1).round(2)


# ---------------------------------------------------------------------------
# Repeat Purchase Rate -- distinct from retention: retention counts who
# bought IN month t, repeat purchase counts who has EVER come back by
# month t (cumulative, monotonic non-decreasing). Needs order_number
# per customer, which add_cohort_fields() above doesn't compute --
# use add_cohort_columns_with_order_number() here instead for this matrix.
# ---------------------------------------------------------------------------


def add_cohort_columns_with_order_number(
    orders: pd.DataFrame,
    customer_col: str = "customer_id",
    order_col: str = "order_id",
    date_col: str = "order_date",
) -> pd.DataFrame:
    data = orders.copy()

    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data = data.dropna(subset=[customer_col, order_col, date_col])
    data = data.sort_values([customer_col, date_col, order_col])

    data["order_month"] = data[date_col].dt.to_period("M")
    data["order_number"] = data.groupby(customer_col).cumcount() + 1
    data["cohort_month"] = data.groupby(customer_col)["order_month"].transform("min")

    data["cohort_index"] = (
        (data["order_month"].dt.year - data["cohort_month"].dt.year) * 12
        + data["order_month"].dt.month
        - data["cohort_month"].dt.month
    )

    return data


def build_repeat_purchase_matrix(
    cohort_orders: pd.DataFrame,
    customer_col: str = "customer_id",
) -> pd.DataFrame:
    """
    cohort_orders: output of add_cohort_columns_with_order_number().
    Month 0 всегда 0%. Month t: доля клиентов когорты, у кого к этому
    моменту УЖЕ был хотя бы один повторный заказ (кумулятивно).
    """
    data = cohort_orders.copy()

    repeat_events = data[data["order_number"] >= 2].copy()

    cohort_sizes = (
        data.groupby("cohort_month")[customer_col].nunique()
        .rename("cohort_size").reset_index()
    )

    all_indices = (
        data[["cohort_month", "cohort_index"]]
        .drop_duplicates()
        .merge(cohort_sizes, on="cohort_month")
    )

    first_repeat = (
        repeat_events
        .groupby(["cohort_month", customer_col], as_index=False)["cohort_index"]
        .min()
        .rename(columns={"cohort_index": "first_repeat_index"})
    )

    records = []

    for cohort_month, cohort_data in all_indices.groupby("cohort_month"):
        cohort_size = int(cohort_data["cohort_size"].iloc[0])

        first_repeats_for_cohort = first_repeat[
            first_repeat["cohort_month"] == cohort_month
        ]

        for cohort_index in sorted(cohort_data["cohort_index"].unique()):
            returned = first_repeats_for_cohort[
                first_repeats_for_cohort["first_repeat_index"] <= cohort_index
            ][customer_col].nunique()

            records.append({
                "cohort_month": cohort_month,
                "cohort_index": cohort_index,
                "repeat_purchase_rate_pct": returned / max(cohort_size, 1) * 100,
            })

    result = pd.DataFrame(records)

    return (
        result
        .pivot(index="cohort_month", columns="cohort_index", values="repeat_purchase_rate_pct")
        .round(1)
    )
