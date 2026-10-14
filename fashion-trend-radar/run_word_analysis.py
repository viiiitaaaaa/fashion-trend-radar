"""
Analytics for the «other words» (user 23.09.2026): phrases from the «Мода — ориентиры» section (fashion Telegram
channels) + growing Pinterest items that passed the season/28+ filters, minus the radar candidates.
Free sources only:
  --pinterest   2-year curve + age/gender via the logged-in Pinterest Trends page (open Dolphin profile 3)
  --google      2-year Google curve via run_trends_bootstrap.py (slow: pauses between words)
  --amazon      Amazon monthly searches via Trends MCP (free quota, amazon source only)
  (no flags)    only compute the verdicts from what is already collected
Verdict = the user's selection rules: growth to last year (Pinterest, stable), autumn-winter season (Google),
audience 28+, real volume.
Output: data/processed/word_analysis.csv
"""
import json
import subprocess
import sys
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from build_dashboard import FASHION_DATA, pinterest_discovery
from src.processors.candidate_matrix import (AUD28_MIN_PINTEREST, MIN_YOY, TARGET_LABEL, in_season_soon, is_stable_growth,
                                             months_label, quarterly_growth, season_calendar, window_stats)

OUT = Path("data/processed/word_analysis.csv")
CURVES = Path("data/processed/word_analysis_pinterest.json")
DEMO = Path("data/processed/pinterest_demographics.csv")
WORDS_1688 = Path("config/words_1688.csv")
AMZ = Path("data/processed/word_analysis_amazon.csv")
AGES = ["18-24", "25-34", "35-44", "45-49", "50-54", "55-64", "65+"]


# Russian channels name things their own way; the same item as people search it in the US (user 23.09.2026:
# «перефразируй и посмотри, пройдут ли они в поиске»). original phrase -> US wordings to check
REPHRASE = {
    "bambi print": ["deer print", "fawn print sweater"],
    "brown shearling jacket": ["shearling jacket women", "brown shearling coat"],
    "burgundy ankle boots": ["burgundy boots", "burgundy boots women"],
    "collared cardigan women": ["collared cardigan", "polo cardigan"],
    "contrast collar jacket women": ["faux fur collar jacket", "collared jacket women"],
    "deer print sweater": ["deer sweater", "reindeer sweater"],
    "frog closure jacket": ["frog button jacket", "toggle coat women"],
    "lace trim sweater": ["lace trim cardigan", "lace cardigan"],
    "mandarin collar blouse": ["mandarin collar shirt", "mandarin collar top"],
    "oxblood loafers": ["burgundy loafers", "oxblood boots"],
    "pink leather jacket": ["pink jacket women"],
    "plaid cuff jeans": ["cuffed jeans", "plaid jeans"],
    "plaid overshirt women": ["plaid shacket", "flannel shacket"],
    "polka dot bomber jacket": ["polka dot jacket", "bomber jacket women"],
    "ribbed beanie": ["ribbed knit beanie", "knit beanie", "beanie women"],
    "rust faux fur coat": ["brown faux fur coat", "faux fur jacket"],
    "shearling lined boots women": ["shearling boots", "shearling lined boots"],
    "western boots women": ["cowboy boots women", "western boots"],
    "chocolate brown boots": ["brown boots women", "brown knee high boots"],
    "suede jacket women": ["suede jacket", "suede jacket women brown"],
    "argyle sweater women": ["argyle sweater"],
    "utility jacket women": ["utility jacket"],
    "wool cardigan women": ["wool cardigan"],
    "snake print boots": ["snakeskin boots", "snake print boots women"],
    "brown shearling jacket ": [],
}


def words():
    """-> {word: source}"""
    out = {}
    if FASHION_DATA.exists():
        for p in json.loads(FASHION_DATA.read_text(encoding="utf-8"))["phrases"]:
            out[p["phrase"]] = "мода Telegram"
    disc, _ = pinterest_discovery()
    for r in disc:
        if r["kind"] == "item" and (r.get("yoy") or 0) >= MIN_YOY and r["season"] == "ours" and not r.get("young"):
            out.setdefault(r["term"], "Pinterest растущие")
    # фасоны товаров с 1688 (таблица cj/katalog_1688_dinamika, 25.09.2026) — проверить их по тем же правилам
    if WORDS_1688.exists():
        for w in pd.read_csv(WORDS_1688)["word"]:
            out.setdefault(w, "товары 1688")
    for orig in list(out):
        for alt in REPHRASE.get(orig, []):
            out.setdefault(alt, f"перефразировка «{orig}»")
    cands = set(pd.read_csv("config/candidates.csv")["candidate"])
    return {w: s for w, s in out.items() if w not in cands}


def short(w):
    return w.replace(" women", "").strip()


def pinterest(ws):
    from playwright.sync_api import sync_playwright
    from run_retailers import cdp_endpoint
    curves = json.loads(CURVES.read_text(encoding="utf-8")) if CURVES.exists() else {}
    demo_rows = []
    get = lambda page, path, params: json.loads(page.evaluate(
        "async u => { const r = await fetch(u); if (r.status !== 200) return 'null'; return await r.text() }",
        f"/{path}/?" + urllib.parse.urlencode(params, safe=",")))
    with sync_playwright() as p:
        page = p.chromium.connect_over_cdp(cdp_endpoint()).contexts[0].new_page()
        try:
            page.goto("https://trends.pinterest.com/?country=US", timeout=60000)
            time.sleep(8)
            end = str(date.today() - timedelta(days=3))
            for i in range(0, len(ws), 10):
                batch = ws[i:i + 10]
                data = get(page, "metrics", {"terms": ",".join(batch), "country": "US", "end_date": end, "days": 730,
                                             "aggregation": 2, "normalize_against_group": "false", "predicted_days": 0}) or []
                for it in data:
                    cs = it.get("counts") or []
                    curves[it["term"]] = {"dates": [c.get("date") for c in cs], "values": [c.get("normalizedCount") for c in cs]}
                time.sleep(1.2)
                dist = get(page, "demographics", {"terms": ",".join(batch), "country": "US", "end_date": end, "days": 90}) or {}
                for term, d in (dist.get("term_distributions") or {}).items():
                    a, g = d.get("age_distribution") or {}, d.get("gender_distribution") or {}
                    demo_rows.append({"term": term, **{f"age_{k}": a.get(k) for k in AGES}, "female": g.get("female"), "male": g.get("male")})
                time.sleep(1.2)
        finally:
            page.close()
        # Pinterest often doesn't know «… women»: retry the short wording and keep it under the original word
        miss = {w: short(w) for w in ws if w not in curves and short(w) != w}
        if miss:
            page = p.chromium.connect_over_cdp(cdp_endpoint()).contexts[0].new_page()
            try:
                page.goto("https://trends.pinterest.com/?country=US", timeout=60000)
                time.sleep(8)
                shorts = list(dict.fromkeys(miss.values()))
                for i in range(0, len(shorts), 10):
                    batch = shorts[i:i + 10]
                    data = get(page, "metrics", {"terms": ",".join(batch), "country": "US", "end_date": end, "days": 730,
                                                 "aggregation": 2, "normalize_against_group": "false", "predicted_days": 0}) or []
                    got = {it["term"]: it for it in data}
                    for w, sw in miss.items():
                        if sw in got:
                            cs = got[sw].get("counts") or []
                            curves[w] = {"dates": [c.get("date") for c in cs], "values": [c.get("normalizedCount") for c in cs], "as": sw}
                    time.sleep(1.2)
                    dist = get(page, "demographics", {"terms": ",".join(batch), "country": "US", "end_date": end, "days": 90}) or {}
                    for term, d in (dist.get("term_distributions") or {}).items():
                        a, g = d.get("age_distribution") or {}, d.get("gender_distribution") or {}
                        for w in [w for w, sw in miss.items() if sw == term]:
                            demo_rows.append({"term": w, **{f"age_{k}": a.get(k) for k in AGES}, "female": g.get("female"), "male": g.get("male")})
                    time.sleep(1.2)
            finally:
                page.close()
    CURVES.write_text(json.dumps(curves, ensure_ascii=False), encoding="utf-8")
    if demo_rows:
        new = pd.DataFrame(demo_rows)
        new["main_age"] = new[[f"age_{k}" for k in AGES]].astype(float).idxmax(axis=1).str.replace("age_", "")
        old = pd.read_csv(DEMO) if DEMO.exists() else pd.DataFrame()
        pd.concat([old[~old["term"].isin(new["term"])] if not old.empty else old, new]).to_csv(DEMO, index=False, encoding="utf-8-sig")
    print(f"Pinterest: кривых {sum(1 for w in ws if w in curves)}/{len(ws)}, возраст {len(demo_rows)}")


def amazon(ws):
    import run_trendsmcp as tm
    old = pd.read_csv(AMZ) if AMZ.exists() else pd.DataFrame(columns=["word"])
    todo = [w for w in ws if w not in set(old["word"])]   # квота 100/мес: уже спрошенные слова не повторяем
    rows = []
    for w in todo:   # amazon only: 1 request per word (no_data answers are free)
        kw, data, err = tm.fetch("amazon", w)
        s = tm.summarize(w, "amazon", kw, data, err)
        rows.append({"word": w, "last_volume": s["last_volume"], "lift_pct": s["lift_pct"], "last_date": s["last_date"], "error": s["error"]})
        time.sleep(1)
    print(f"Amazon: спросили {len(todo)} новых слов из {len(ws)}")
    pd.concat([old, pd.DataFrame(rows)]).drop_duplicates("word", keep="last").to_csv(AMZ, index=False, encoding="utf-8-sig")


def verdicts(ws):
    curves = json.loads(CURVES.read_text(encoding="utf-8")) if CURVES.exists() else {}
    for f in ("data/processed/pinterest_discovery_curves.json",):
        if Path(f).exists():
            for k, v in json.loads(Path(f).read_text(encoding="utf-8")).items():
                curves.setdefault(k, v)
    demo = pd.read_csv(DEMO).drop_duplicates("term", keep="last").set_index("term") if DEMO.exists() else pd.DataFrame()
    g = pd.read_parquet("data/normalized/google_trends")
    g = g[(g["region"] == "US") & ~g["is_partial"].astype(bool)].sort_values("date").drop_duplicates(["date", "keyword"], keep="last")
    amz = pd.read_csv("data/processed/word_analysis_amazon.csv").set_index("word") if Path("data/processed/word_analysis_amazon.csv").exists() else pd.DataFrame()
    rows = []
    for w, src in ws.items():
        r = {"word": w, "source": src}
        c = curves.get(w)
        vals = [v for v in (c or {}).get("values", []) if v is not None]
        st, q = window_stats(vals), quarterly_growth(vals)
        r["pin_yoy"] = st["yoy_pct"] if st else None
        r["pin_stable"] = is_stable_growth(st, q)
        r["pin_weeks"] = len(vals)
        gh = g[g["keyword"] == w]
        months = season_calendar(list(gh["date"]), list(gh["interest"])) if len(gh) else None
        gst = window_stats(list(gh["interest"])) if len(gh) else None
        r["google_yoy"] = gst["yoy_pct"] if gst else None
        r["season"] = months_label(months)
        r["in_season"] = in_season_soon(months, date.today().month) if months else None
        if w in demo.index:
            d = demo.loc[w]
            ages = [f"age_{k}" for k in AGES if f"age_{k}" in demo.columns]
            tot = sum(float(d[a]) for a in ages if pd.notna(d[a]))
            r["aud28"] = round((0.7 * float(d["age_25-34"]) + sum(float(d[a]) for a in ages[2:] if pd.notna(d[a]))) / tot * 100) if tot else None
            r["main_age"] = d.get("main_age")
            r["female"] = round(float(d["female"]) * 100) if pd.notna(d.get("female")) else None
        fresh_amz = w in amz.index and (pd.isna(amz.loc[w].get("last_date")) or
                                        pd.Timestamp(amz.loc[w]["last_date"]) >= pd.Timestamp.today() - pd.Timedelta(days=62))
        if w in amz.index and not fresh_amz and pd.notna(amz.loc[w].get("last_volume")):
            r["amazon_stale"] = str(amz.loc[w]["last_date"])[:7]
        if w in amz.index and fresh_amz and pd.notna(amz.loc[w].get("last_volume")):
            r["amazon_searches"] = int(amz.loc[w]["last_volume"])
            r["amazon_lift"] = amz.loc[w].get("lift_pct")
        # the user's rules, in her order
        why = []
        has_pin = bool(vals) and sum(1 for v in vals if v) / len(vals) >= 0.5
        r["growth_by"] = "Pinterest" if has_pin else ("Google" if r["google_yoy"] is not None else "")
        if has_pin:
            if r["pin_yoy"] is None or r["pin_yoy"] < MIN_YOY:
                why.append(f"нет роста к году по Pinterest ({r['pin_yoy']:+.0f}%)" if r["pin_yoy"] is not None else "рост не посчитать")
            elif not r["pin_stable"]:
                why.append("рост нестабильный (меньше 3 из 4 кварталов)")
        elif r["google_yoy"] is not None:   # Pinterest doesn't know the phrase -> Google, last 8 weeks vs a year ago
            if r["google_yoy"] < MIN_YOY:
                why.append(f"нет роста к году по Google ({r['google_yoy']:+.0f}%)")
        else:
            why.append("слишком редкий запрос: ни Pinterest, ни Google не дают данных")
        if r["in_season"] is False:
            why.append(f"не наш сезон ({r['season']})")
        if r.get("main_age") == "18-24":
            why.append("главная аудитория 18–24")
        elif r.get("aud28") is not None and r["aud28"] < AUD28_MIN_PINTEREST:
            why.append(f"мало аудитории 28+ ({r['aud28']}%)")
        if r.get("female") is not None and r["female"] < 50:
            why.append(f"в основном не женщины (женщин {r['female']}% на Pinterest)")
        small = r.get("amazon_searches") is not None and r["amazon_searches"] < 2000
        if not why and small:
            why.append(f"маленький спрос на Amazon ({r['amazon_searches']:,}/мес)".replace(",", " "))
        if not why and r.get("amazon_searches") is None:   # rule 6: real volume; growth from ~0 is not proof
            why.append("объём неизвестен: на Amazon фразу не ищут, рост может быть «с нуля»")
        soft = len(why) == 1 and (why[0].startswith("рост нестаб") or why[0].startswith("маленький") or why[0].startswith("объём неизв"))
        r["verdict"] = "в кандидаты" if not why else ("наблюдать" if soft else "не проходит")
        gr = r["pin_yoy"] if r["growth_by"] == "Pinterest" else r["google_yoy"]
        r["why"] = "; ".join(why) if why else (f"растёт к году ({gr:+.0f}% по {r['growth_by']}), сезон {r['season'] or 'не определён'}"
                                                + (f", аудитория 28+ {r['aud28']}%" if r.get("aud28") is not None else ""))
        rows.append(r)
    df = pd.DataFrame(rows)
    order = {"в кандидаты": 0, "наблюдать": 1, "не проходит": 2}
    df = df.sort_values(["verdict", "pin_yoy"], key=lambda s: s.map(order) if s.name == "verdict" else -s.fillna(-1e9))
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(df[[c for c in ["word", "verdict", "pin_yoy", "google_yoy", "season", "aud28", "amazon_searches", "why"] if c in df]].to_string(index=False))


def main():
    ws = words()
    print(f"{len(ws)} слов")
    flags = set(sys.argv[1:])
    if "--pinterest" in flags:
        pinterest(list(ws))
    if "--google" in flags or "--google-new" in flags:
        have = set(pd.read_parquet("data/normalized/google_trends")["keyword"])
        todo = [w for w in ws if w not in have] if "--google-new" in flags else [w for w in ws]
        subprocess.run([sys.executable, "run_trends_bootstrap.py", *todo], check=False)
    if "--amazon" in flags:
        amazon(list(ws))
    verdicts(ws)


if __name__ == "__main__":
    main()
