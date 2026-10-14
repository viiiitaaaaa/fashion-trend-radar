"""
Candidate discovery channel #1: Google Trends RISING related queries for
broad women's-fashion seeds (US, 90 days). Sequential, 15-35s between seeds.
Output: data/processed/candidates_google_rising.csv
"""

import random
import time
from pathlib import Path

import pandas as pd

from src.collectors.google_trends_cached import get_related_queries_cached
from src.processors.fashion_taxonomy import decompose_keywords

SEEDS = [
    "skirt", "dress", "womens top", "blouse", "sweater",
    "cardigan", "womens pants", "womens jeans", "womens jacket", "womens coat",
]


def main():
    frames = []
    for i, seed in enumerate(SEEDS, 1):
        print(f"[{i}/{len(SEEDS)}] {seed}")
        try:
            frames.append(get_related_queries_cached(seed, geo="US", days=90))
        except RuntimeError as e:
            print(f"SKIPPED: {e}")
        if i < len(SEEDS):
            time.sleep(random.uniform(15, 35))

    if not frames:
        print("Ничего не собрано.")
        return

    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={"query": "keyword"})
    df = decompose_keywords(df, keyword_col="keyword")
    df = df.sort_values(["seed", "value"], ascending=[True, False])

    out = Path("data/processed/candidates_google_rising.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")

    print(f"\nВсего растущих запросов: {len(df)}, breakout: {int(df['is_breakout'].sum())}")
    for seed, g in df.groupby("seed"):
        top = ", ".join(f"{k} (+{int(v)}%)" for k, v in zip(g["keyword"].head(5), g["value"].head(5)))
        print(f"  {seed}: {top}")
    print(f"Сохранено: {out}")


if __name__ == "__main__":
    main()
