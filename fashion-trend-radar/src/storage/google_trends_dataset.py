"""
Long-term partitioned Parquet dataset for normalized Google Trends history
-- distinct from google_trends_cached.py's per-keyword TTL cache
(data/cache/google_trends/). This is the durable store you'd query across
keywords/time; the cache is just "did we already ask Google today".
Partitioned by source/region/year/month, deliberately NOT by keyword
(100-1000 keywords would create too many small files).
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd


DATASET_ROOT = Path("data/normalized/google_trends")


def add_partition_columns(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()

    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date", "region"])

    data["year"] = data["date"].dt.year.astype("int16")
    data["month"] = data["date"].dt.month.astype("int8")

    data["interest"] = pd.to_numeric(
        data["interest"], errors="coerce"
    ).fillna(0).astype("float32")

    data["keyword"] = data["keyword"].astype("string")
    data["region"] = data["region"].astype("string")
    data["is_partial"] = data["is_partial"].astype(bool)

    return data


def write_partitioned_dataset(df: pd.DataFrame, root: Path = DATASET_ROOT) -> None:
    data = add_partition_columns(df)

    data.to_parquet(
        path=root,
        engine="pyarrow",
        compression="zstd",
        index=False,
        partition_cols=["region", "year", "month"],
    )


def read_google_trends_slice(
    root: Path = DATASET_ROOT,
    region: str = "US",
    year: int = 2026,
    month: int | None = None,
) -> pd.DataFrame:
    """Dedupes on read (date, keyword, region) since to_parquet() appends
    new part files rather than overwriting same-day data -- fine for this
    project's scale, avoid it if the dataset grows past a few GB."""
    filters = [("region", "==", region), ("year", "==", year)]

    if month is not None:
        filters.append(("month", "==", month))

    data = pd.read_parquet(root, engine="pyarrow", filters=filters)

    data = data.sort_values("date")
    data = data.drop_duplicates(subset=["date", "keyword", "region"], keep="last")

    return data.reset_index(drop=True)
