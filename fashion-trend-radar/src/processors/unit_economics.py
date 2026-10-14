"""
CAC and LTV -- independent of trend scoring. Useless until real Shopify
order data exists; until then use it only to sanity-check an assumed CAC
against the contribution margin of a single order (see fashion_score.py's
margin_score), not to "predict" anything. See TZ_trend_scoring.md.
"""

from __future__ import annotations

import pandas as pd


def calculate_cac(
    marketing_spend: float,
    new_customers: int
) -> float:
    if new_customers <= 0:
        return 0.0

    return round(
        marketing_spend / new_customers,
        2
    )


def calculate_customer_ltv(
    orders: pd.DataFrame,
    customer_col: str = "customer_id",
    revenue_col: str = "revenue",
    cogs_col: str = "cogs",
    shipping_col: str = "shipping_cost",
    payment_fee_col: str = "payment_fee",
    refund_col: str = "refund_amount"
) -> pd.DataFrame:
    data = orders.copy()

    money_cols = [
        revenue_col,
        cogs_col,
        shipping_col,
        payment_fee_col,
        refund_col,
    ]

    for col in money_cols:
        data[col] = pd.to_numeric(
            data[col],
            errors="coerce"
        ).fillna(0)

    data["contribution_profit"] = (
        data[revenue_col]
        - data[cogs_col]
        - data[shipping_col]
        - data[payment_fee_col]
        - data[refund_col]
    )

    ltv = (
        data
        .groupby(customer_col, as_index=False)
        .agg(
            order_count=(customer_col, "size"),
            gross_revenue=(revenue_col, "sum"),
            contribution_ltv=(
                "contribution_profit",
                "sum",
            ),
            total_refunds=(refund_col, "sum"),
        )
    )

    ltv["aov"] = (
        ltv["gross_revenue"] / ltv["order_count"]
    ).round(2)

    return ltv


# ---------------------------------------------------------------------------
# Fuller cost model (discounts, ad_spend, creator_cost included) + batch CAC
# by period/channel. Prefer these for new work; the plain calculate_cac() /
# calculate_customer_ltv() above still work for a quick one-off scalar CAC
# or when you don't yet track discounts/ad_spend/creator_cost per order.
# ---------------------------------------------------------------------------

MONEY_COLUMNS = [
    "gross_revenue",
    "discount_amount",
    "refund_amount",
    "cogs",
    "shipping_cost",
    "payment_fee",
    "ad_spend",
    "creator_cost",
    "variable_support_cost",
]


def prepare_order_economics(orders: pd.DataFrame) -> pd.DataFrame:
    """Contribution Profit = Net Revenue - COGS - Shipping - Payment Fees
    - Ad Spend - Creator Cost - Variable Support. For organic TikTok/
    Pinterest, ad_spend can stay 0, but track creator_cost separately if
    you pay UGC creators."""
    data = orders.copy()

    for col in MONEY_COLUMNS:
        if col not in data.columns:
            data[col] = 0.0

        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0.0)

    data["net_revenue"] = (
        data["gross_revenue"] - data["discount_amount"] - data["refund_amount"]
    )

    data["variable_costs"] = (
        data["cogs"]
        + data["shipping_cost"]
        + data["payment_fee"]
        + data["ad_spend"]
        + data["creator_cost"]
        + data["variable_support_cost"]
    )

    data["contribution_profit"] = data["net_revenue"] - data["variable_costs"]

    data["contribution_margin_pct"] = (
        data["contribution_profit"] / data["gross_revenue"].clip(lower=0.01) * 100
    )

    return data


def calculate_cac_batch(
    acquisition_costs: pd.DataFrame,
    spend_col: str = "spend",
    new_customers_col: str = "new_customers",
) -> pd.DataFrame:
    """Vectorized CAC per row (e.g. per period/channel) -- for a single
    scalar CAC use calculate_cac() above."""
    data = acquisition_costs.copy()

    data[spend_col] = pd.to_numeric(data[spend_col], errors="coerce").fillna(0)
    data[new_customers_col] = pd.to_numeric(
        data[new_customers_col], errors="coerce"
    ).fillna(0)

    data["cac"] = data[spend_col] / data[new_customers_col].clip(lower=1)

    # Если новых покупателей не было, CAC неизвестен, а не равен $0.
    data.loc[data[new_customers_col] == 0, "cac"] = pd.NA

    return data


def calculate_customer_ltv_from_prepared(
    prepared_orders: pd.DataFrame,
    customer_col: str = "customer_id",
) -> pd.DataFrame:
    """Run prepare_order_economics() first -- needs its contribution_profit
    and net_revenue columns."""
    data = prepared_orders.copy()

    result = (
        data
        .groupby(customer_col, as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            gross_revenue=("gross_revenue", "sum"),
            net_revenue=("net_revenue", "sum"),
            contribution_ltv=("contribution_profit", "sum"),
            refunds=("refund_amount", "sum"),
        )
    )

    result["aov"] = result["gross_revenue"] / result["orders"].clip(lower=1)
    result["refund_rate"] = result["refunds"] / result["gross_revenue"].clip(lower=0.01)

    return result


# ---------------------------------------------------------------------------
# Discounted LTV, CAC by channel, payback month. Discounted contribution LTV
# is preferred over the plain cumulative LTV above once you're comparing
# channels/cohorts with different time horizons -- a dollar of contribution
# profit 12 months out isn't worth the same as one in month 0.
# ---------------------------------------------------------------------------


def build_discounted_ltv_matrix(
    cohort_orders: pd.DataFrame,
    annual_discount_rate: float = 0.20,
    customer_col: str = "customer_id",
) -> pd.DataFrame:
    """
    cohort_orders: needs cohort_month/cohort_index (from
    cohort_analysis.add_cohort_fields()) AND contribution_profit (from
    prepare_order_economics()) already merged onto the same rows.

    Возвращает cumulative discounted contribution LTV на одного
    первоначального клиента в когорте. annual_discount_rate=0.20 = 20%
    годовых; задай свою hurdle rate под internal planning.
    """
    data = cohort_orders.copy()

    if "contribution_profit" not in data.columns:
        raise ValueError("Run prepare_order_economics() first.")
    if "cohort_month" not in data.columns or "cohort_index" not in data.columns:
        raise ValueError(
            "Run cohort_analysis.add_cohort_fields() first."
        )

    monthly = (
        data
        .groupby(["cohort_month", "cohort_index"], as_index=False)
        .agg(contribution_profit=("contribution_profit", "sum"))
    )

    cohort_size = (
        data.groupby("cohort_month")[customer_col].nunique()
        .rename("cohort_size").reset_index()
    )

    monthly = monthly.merge(cohort_size, on="cohort_month", how="left")

    monthly["monthly_ltv_per_customer"] = (
        monthly["contribution_profit"] / monthly["cohort_size"].clip(lower=1)
    )

    monthly["discount_factor"] = (
        (1 + annual_discount_rate) ** (monthly["cohort_index"] / 12)
    )

    monthly["discounted_ltv_per_customer"] = (
        monthly["monthly_ltv_per_customer"] / monthly["discount_factor"]
    )

    matrix = monthly.pivot(
        index="cohort_month", columns="cohort_index", values="discounted_ltv_per_customer",
    )

    return matrix.cumsum(axis=1).round(2)


def calculate_cac_by_channel(
    acquisition: pd.DataFrame,
    spend_col: str = "acquisition_spend",
    customers_col: str = "new_customers",
) -> pd.DataFrame:
    """Same shape as calculate_cac_batch() above, named to match the
    channel-level acquisition table this is meant to run on. Don't count
    repeat purchases in the denominator; for organic TikTok/Pinterest still
    count UGC/shoot/tooling spend so CAC isn't falsely $0."""
    data = acquisition.copy()

    data[spend_col] = pd.to_numeric(data[spend_col], errors="coerce").fillna(0)
    data[customers_col] = pd.to_numeric(data[customers_col], errors="coerce").fillna(0)

    data["cac"] = data[spend_col] / data[customers_col].clip(lower=1)
    data.loc[data[customers_col] == 0, "cac"] = pd.NA

    return data


def find_payback_month(
    cumulative_discounted_ltv: pd.Series,
    cac: float,
) -> int | None:
    """cumulative_discounted_ltv: one row of build_discounted_ltv_matrix(),
    index = cohort_index (0, 1, 2, ...). Returns the first month cumulative
    discounted LTV reached CAC, or None if it never did in the data."""
    paid_back = cumulative_discounted_ltv[cumulative_discounted_ltv >= cac]

    if paid_back.empty:
        return None

    return int(paid_back.index[0])
