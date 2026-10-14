"""
TikTok Shop (US) search for OUR candidates via treg.to (TikHub, $0.001 per call): what similar products already
sell there. Page 1 of search = 30 products: sold counts, prices, reviews, sellers. Runs only by hand.

    .venv/Scripts/python.exe run_tiktok_shop.py                  # all candidates
    .venv/Scripts/python.exe run_tiktok_shop.py "bandana cardigan"

Output: data/processed/tiktok_shop.csv (one row per candidate), data/processed/tiktok_shop_products.csv
"""
import json
import statistics
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import dotenv_values

env = dotenv_values(".env")
H = {"X-Treg-Token": env["TREG_TOKEN"], "X-Treg-Org": env.get("TREG_ORG", "vi")}
ENDPOINT = "tikhub.x.tiktok-shop-web-fetch-search-products-list"
RAW = Path("data/raw/treg")
spent = 0.0


PAGES = 3   # 30 products a page; pages 2-3 via load_more_params (offset + page_token)


def search(word):
    global spent
    out, params = [], {"search_word": word, "region": "US", "offset": 0}
    for page in range(PAGES):
        r = requests.get(f"https://treg.to/call/{ENDPOINT}", headers=H, params=params, timeout=90)
        spent += int(r.headers.get("X-Treg-Cost-Micro") or 0) / 1e6
        d = r.json()
        (RAW / f"{datetime.now():%Y%m%d_%H%M%S}_tiktokshop_{word.replace(' ', '-')}_p{page + 1}.json").write_text(
            json.dumps(d, ensure_ascii=False), encoding="utf-8")
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} {str(d)[:200]}")
        out += parse(d)
        inner = (d.get("data") or {}).get("data") or {}
        more = inner.get("load_more_params") or {}
        if str(inner.get("has_more")).lower() != "true" or not more.get("page_token"):
            break
        params = {"search_word": word, "region": "US", "offset": more.get("offset", 30 * (page + 1)),
                  "page_token": more["page_token"]}
    return list({p["product_id"]: p for p in out}.values())   # pages can repeat a product


def parse(d):
    data = d.get("data") or {}
    data = data.get("data") or data          # TikHub wraps the payload twice
    out = []
    for p in (data.get("products") or []):
        price = (p.get("product_price_info") or {}).get("sale_price_decimal")
        out.append({
            "product_id": p.get("product_id"),
            "link": f"https://www.tiktok.com/view/product/{p.get('product_id')}",
            "title": (p.get("title") or "")[:140],
            "price": float(price) if price not in (None, "") else None,
            "sold": int((p.get("sold_info") or {}).get("sold_count") or 0),
            "reviews": int((p.get("rate_info") or {}).get("review_count") or 0),
            "shop": (p.get("seller_info") or {}).get("shop_name") or "",
        })
    return out


def save_merged(df_new, path, key="candidate"):
    """Partial runs (a few candidates) must not wipe the others: replace only the rows of the candidates just collected."""
    path = Path(path)
    if df_new.empty and path.exists():
        return   # nothing collected (provider error) — keep what is there
    if path.exists() and not df_new.empty and key in df_new:
        old = pd.read_csv(path)
        if key in old:
            df_new = pd.concat([old[~old[key].isin(df_new[key].unique())], df_new], ignore_index=True)
    df_new.to_csv(path, index=False, encoding="utf-8-sig")


def main():
    from_raw = "--from-raw" in sys.argv          # re-read today's saved answers, no new (paid) calls
    cands = [a for a in sys.argv[1:] if not a.startswith("--")] or pd.read_csv("config/candidates.csv")["candidate"].tolist()
    summary, products = [], []
    for c in cands:
        try:
            if from_raw:
                f = sorted(RAW.glob(f"{date.today():%Y%m%d}_*_tiktokshop_{c.replace(' ', '-')}*.json"))
                ps = list({p["product_id"]: p for x in f for p in parse(json.loads(x.read_text(encoding="utf-8")))}.values())
            else:
                ps = search(c)
        except (RuntimeError, ValueError) as e:
            print(f"  {c}: {e}")
            ps = []
        for p in ps:
            p["candidate"] = c
        products += ps
        prices = [p["price"] for p in ps if p["price"]]
        top = sorted(ps, key=lambda p: p["sold"], reverse=True)
        summary.append({
            "candidate": c, "products": len(ps), "sold_total": sum(p["sold"] for p in ps),
            "sold_top": top[0]["sold"] if top else 0, "sellers": len({p["shop"] for p in ps}),
            "with_sales": sum(1 for p in ps if p["sold"] > 0),
            "price_median": round(statistics.median(prices), 2) if prices else None,
            "date": str(date.today()),
        })
        s = summary[-1]
        print(f"  {c:<24} товаров {s['products']:>2}, продано всего {s['sold_total']:>9,}, лидер {s['sold_top']:>8,}, "
              f"продавцов {s['sellers']:>2}, цена ~${s['price_median']}")
    out = Path("data/processed")
    save_merged(pd.DataFrame(summary), out / "tiktok_shop.csv")
    save_merged(pd.DataFrame(products), out / "tiktok_shop_products.csv")
    print(f"Потрачено: ${spent:.4f}. Сохранено: tiktok_shop.csv, tiktok_shop_products.csv")


if __name__ == "__main__":
    main()
