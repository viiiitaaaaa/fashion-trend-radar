"""
Сверка trendsmcp.ai (google search) с нашим Google Trends на одних и тех же неделях.
Запуск: python compare_trendsmcp.py "roll neck sweater" "plaid skirt" ...
Если свежий ответ trendsmcp уже лежит в data/raw/trendsmcp/ (моложе 3 дней) — квоту не тратит.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.clients import trendsmcp_client as tm

# trendsmcp метит неделю её концом (суббота), Google Trends — началом (воскресенье)
MCP_SHIFT_DAYS = int(dict(a.split("=") for a in sys.argv[1:] if a.startswith("shift=")).get("shift", -6))


def mcp_series(keyword: str) -> pd.Series:
    slug = keyword.replace(" ", "-")
    cached = sorted(tm.RAW.glob(f"*_get_time_series_google-search_{slug}.json"))
    fresh = [p for p in cached
             if datetime.now() - datetime.strptime(p.name[:15], "%Y%m%d_%H%M%S") < timedelta(days=3)]
    data = json.loads(fresh[-1].read_text(encoding="utf-8")) if fresh else tm.time_series("google search", keyword)
    rows = json.loads(data["body"]) if isinstance(data, dict) and "body" in data else data
    s = pd.Series({pd.Timestamp(r["date"]) + pd.Timedelta(days=MCP_SHIFT_DAYS): r["value"] for r in rows})
    return s.sort_index()


def main(keywords):
    ours = pd.read_parquet("data/normalized/google_trends")
    out = []
    for kw in keywords:
        mcp = mcp_series(kw)
        g = ours[ours.keyword == kw].set_index("date")["interest"]
        g.index = pd.to_datetime(g.index)
        both = pd.concat({"google": g, "trendsmcp": mcp}, axis=1, join="inner").dropna()
        both = both / both.max() * 100  # одно окно, пик = 100 в каждом ряду
        last4 = both.tail(4).mean()
        prev4 = both.iloc[-8:-4].mean()
        out.append({
            "keyword": kw,
            "weeks": len(both),
            "corr": round(both["google"].corr(both["trendsmcp"]), 2),
            "mean_abs_diff": round((both["google"] - both["trendsmcp"]).abs().mean(), 1),
            "growth_google_%": round((last4["google"] / prev4["google"] - 1) * 100),
            "growth_mcp_%": round((last4["trendsmcp"] / prev4["trendsmcp"] - 1) * 100),
        })
        print(f"\n== {kw} ==")
        print(both.round(0).astype(int).to_string())
    res = pd.DataFrame(out)
    print("\n", res.to_string(index=False))
    Path("data/reports").mkdir(parents=True, exist_ok=True)
    res.to_csv(f"data/reports/trendsmcp_vs_google_{datetime.now():%Y%m%d}.csv", index=False)
    print(f"\nПотрачено запросов trendsmcp в этом месяце: {tm.used_this_month()}/{tm.FREE_MONTHLY}")


if __name__ == "__main__":
    kws = [a for a in sys.argv[1:] if not a.startswith("shift=")]
    main(kws or ["roll neck sweater", "plaid skirt", "faux fur coat"])
