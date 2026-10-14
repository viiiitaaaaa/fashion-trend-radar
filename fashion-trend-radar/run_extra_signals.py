"""
Extra signals for candidates the radar can't see well (user request 22.09.2026).
One Dolphin run (profile 859648353), human pace, no protection bypass:

  --pinterest  other wordings for candidates Pinterest Trends doesn't track
               -> data/raw/pinterest_trends/variants_<date>.json (same format as metrics_*.json)
  --amazon     Amazon search page 1 per candidate: sum of "N+ bought in past month" badges
               -> data/processed/amazon_bought.csv

    .venv/Scripts/python.exe run_extra_signals.py --pinterest --amazon
"""
import json
import random
import re
import sys
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, r"C:\Users\User\dolphin_anty")
from dolphin import DolphinLocal, start_with_retry  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from run_pinterest_trends import PAGE_PARAMS, PROFILE, URL as PIN_URL, fetch_metrics  # noqa: E402

VARIANTS = {   # candidate -> wordings to try on Pinterest Trends
    "bandana cardigan": ["bandana print cardigan", "bandana sweater", "paisley cardigan",
                         "paisley sweater", "bandana knit sweater", "gap bandana cardigan"],
    "fall cardigan": ["oversized cardigan", "cropped cardigan", "chunky cardigan",
                      "cardigan outfit", "long cardigan", "cardigan"],
}
BOUGHT = re.compile(r"([\d.,]+)\s*(K)?\+?\s*bought in past month", re.I)
MAX_CAPTCHAS = 2


def pinterest(page):
    def on_resp(resp):
        if "/metrics/?terms=" in resp.url:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(resp.url).query)
            if q.get("end_date"):
                PAGE_PARAMS["end_date"] = q["end_date"][0]
    page.on("response", on_resp)
    page.goto(PIN_URL, timeout=90000, wait_until="domcontentloaded")
    for _ in range(10):          # wait until the page's own metrics call gives us a valid end_date
        if PAGE_PARAMS["end_date"]:
            break
        page.mouse.wheel(0, 800)
        time.sleep(2)
    page.remove_listener("response", on_resp)
    if not PAGE_PARAMS["end_date"]:   # today has no data yet on Pinterest -> 400
        PAGE_PARAMS["end_date"] = str(date.today() - timedelta(days=7))
    print(f"Pinterest end_date: {PAGE_PARAMS['end_date']}")

    terms = [t for v in VARIANTS.values() for t in v]
    dump = {}
    for i in range(0, len(terms), 10):
        batch = terms[i:i + 10]
        try:
            dump[",".join(batch)] = fetch_metrics(page, batch)
        except RuntimeError:     # one unknown wording can fail the batch -> ask term by term
            for t in batch:
                try:
                    dump[t] = fetch_metrics(page, [t])
                except RuntimeError as e:
                    print(f"   {t}: {e}")
                time.sleep(random.uniform(2, 4))
        time.sleep(random.uniform(4, 8))
    out = Path("data/raw/pinterest_trends") / f"variants_{date.today()}.json"
    out.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")

    print("\n=== Pinterest: какие формулировки есть в трендах ===")
    got = {t["term"]: t for batch in dump.values() for t in batch if t}
    for cand, variants in VARIANTS.items():
        print(f"{cand}:")
        for v in variants:
            t = got.get(v)
            if not t:
                print(f"   {v:<24} — нет данных")
                continue
            g = t.get("growth_rates") or {}
            pct = lambda x: f"{x * 100:+.0f}%" if isinstance(x, (int, float)) else "—"
            print(f"   {v:<24} недель {len(t.get('counts', [])):>3}  месяц {pct(g.get('mom_change')):>6}  год {pct(g.get('yoy_change')):>6}")
    print(f"Сохранено: {out}")


def parse_bought(html):
    s = BeautifulSoup(html, "html.parser")
    items = s.select('div[data-component-type="s-search-result"]')
    rows = []
    for it in items:
        m = BOUGHT.search(it.get_text(" ", strip=True))
        n = None
        if m:
            n = float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
        title = it.select_one("h2")
        rows.append((title.get_text(" ", strip=True)[:90] if title else "", n))
    return rows


def amazon(page):
    candidates = pd.read_csv("config/candidates.csv")["candidate"].tolist()
    out, captchas = [], 0
    for cand in candidates:
        q = cand if "women" in cand else f"{cand} women"
        page.goto(f"https://www.amazon.com/s?k={urllib.parse.quote_plus(q)}&i=fashion",
                  timeout=90000, wait_until="domcontentloaded")
        time.sleep(random.uniform(3, 5))
        if "validateCaptcha" in page.content() or "/errors/" in page.url:
            captchas += 1
            print(f"  {cand}: Amazon показал проверку ({captchas}/{MAX_CAPTCHAS}) — пропускаю")
            if captchas >= MAX_CAPTCHAS:
                print("  Стоп: вторая проверка подряд, дальше не идём (обход запрещён правилами).")
                break
            time.sleep(random.uniform(20, 30))
            continue
        for _ in range(4):
            page.mouse.wheel(0, 1500)
            time.sleep(random.uniform(0.8, 1.5))
        rows = parse_bought(page.content())
        with_badge = [n for _, n in rows if n]
        top = sorted(((n, t) for t, n in rows if n), reverse=True)[:3]
        out.append({
            "candidate": cand, "query": q, "items": len(rows), "items_with_bought": len(with_badge),
            "bought_sum": int(sum(with_badge)), "bought_max": int(max(with_badge)) if with_badge else 0,
            "top": " | ".join(f"{int(n)}+ {t}" for n, t in top), "date": str(date.today()),
        })
        print(f"  {cand:<24} товаров {len(rows):>3}, с пометкой {len(with_badge):>3}, куплено ≥ {int(sum(with_badge)):>7}")
        time.sleep(random.uniform(8, 15))
    if out:
        p = Path("data/processed/amazon_bought.csv")
        pd.DataFrame(out).to_csv(p, index=False, encoding="utf-8-sig")
        print(f"Сохранено: {p}")


def main():
    flags = set(sys.argv[1:])
    api = DolphinLocal(port=DolphinLocal.discover() or 3001)
    auto = start_with_retry(api, PROFILE, no_tabs=True)["automation"]
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"ws://127.0.0.1:{auto['port']}{auto['wsEndpoint']}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        if "--pinterest" in flags:
            try:
                pinterest(page)
            except Exception as e:   # Pinterest failing must not cost us the Amazon part
                print(f"Pinterest: ошибка {e!r} — перехожу к Amazon")
        if "--amazon" in flags:
            print("\n=== Amazon: «bought in past month», первая страница поиска ===")
            amazon(page)
        page.close()


if __name__ == "__main__":
    main()
