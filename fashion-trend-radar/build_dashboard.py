"""
Builds the Trend Radar dashboard (single self-contained HTML) from the latest
radar outputs. Re-run after run_radar.py, then publish the file.
Output: data/reports/trend_radar_dashboard.html
"""
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from radar_curves import build_block
from src.processors.candidate_matrix import AUD28_MIN_PINTEREST, sort_candidates

LOCAL = Path(r"C:\Users\User\dolphin_anty\trend_radar_dashboard.html")

CHANNELS = [
    {"key": "check_google", "short": "G", "name": "Google", "status": "ok",
     "note": "растущие запросы (10 широких слов) + история за 2 года: 8 недель к тем же неделям прошлого года"},
    {"key": "check_pinterest", "short": "P", "name": "Pinterest", "status": "ok",
     "note": "2 года по неделям: рост к прошлому году в среднем за 8 недель, метка сезона"},
    {"key": "check_youtube", "short": "Y", "name": "YouTube", "status": "ok",
     "note": "поиск на YouTube за 2 года (Google Trends) + YouTube API для лидеров: просмотры свежих видео к прошлому году, комментарии «где купить»"},
    {"key": "check_tiktok", "short": "T", "name": "TikTok", "status": "partial",
     "note": "90 дней; видна только мода из общего топ-100 — фильтр «Одежда» пока не работает. "
             "Trends MCP: объём хэштега по дням, но только у крупных (#falloutfit)"},
    {"key": "check_amazon", "short": "A", "name": "Amazon", "status": "ok",
     "note": "новинки + хиты продаж в 8 разделах женской одежды; "
             "Trends MCP: сколько раз вещь искали на Amazon за месяц и рост к прошлому месяцу"},
    {"key": "check_retailers", "short": "R", "name": "Бренды", "status": "ok",
     "note": "новинки Zara, ASOS, Aritzia, Free People, H&M, Urban Outfitters, Abercrombie + Mango"},
    {"key": "check_instagram", "short": "I", "name": "Instagram", "status": "ok",
     "note": "свежие посты под хэштегом вещи (весь мир, treg.to): засчитывается при ≥1 посте в день и последнем посте не старше недели"},
]
INFO_CHANNELS = [   # shown on the card, not a vote in the 7 checks
    ("Temu", "поиск Temu США через ваш вход в профиле Dolphin 3: сколько похожих товаров и продаж на 1-й странице (run_temu.py)"),
    ("Насыщение Amazon", "товаров, брендов и отзывов на 1-й странице поиска (run_saturation.py)"),
    ("Реклама конкурентов (Meta, США)", "сайт Ad Library через профиль 3: сколько объявлений, рекламодателей и сколько идут 30+ дней (run_meta_adlib_web.py)"),
    ("Реклама в Европе (Meta API)", "официальный API, реклама в ЕС/Великобритании + охват по возрасту (run_meta_ads.py) — нужен токен в .env"),
]
PENDING = [
    ("Etsy", "Etsy заблокировал ключ (Banned) — канал закрыт"),
    ("Reddit", "для коммерческого использования нужно письменное одобрение Reddit — пока исключён"),
    ("Keyword Tool", "платный тариф"),
]


def data_gaps(cand):
    """What the radar is still missing, with live coverage counts from the current data."""
    n = len(cand)
    cnt = lambda col: int(cand[col].notna().sum()) if col in cand else 0
    amazon_days = sorted({p.stem[-10:] for p in Path("data/normalized/amazon").glob("amazon_*.parquet")})
    brand_days = sorted({p.stem[-10:] for p in Path("data/normalized/retailers").glob("retailers_*.parquet")})
    return [
        {"what": "TikTok США по хэштегам", "have": f"живых {int(cand['check_tiktok'].sum())} из {n}",
         "why": "собирается через treg.to по команде (~$0.003 на вещь); настоящей кривой интереса TikTok не отдаёт — "
                "график строится по датам видео", "fix": "run_tiktok_tags.py по команде"},
        {"what": "Instagram", "have": f"живых {int(cand['check_instagram'].sum())} из {n}" if "check_instagram" in cand else "—",
         "why": "только весь мир (фильтра по стране нет), по ~36 свежим постам", "fix": "run_instagram_tags.py по команде"},
        {"what": "Pinterest-кривые", "have": f"{cnt('pin_yoy_pct')} из {n}",
         "why": "по редким фразам Pinterest данных не даёт", "fix": "подбирать формулировки, которые Pinterest знает"},
        {"what": "YouTube: видео и «где купить»", "have": f"{cnt('yt_views_90d')} из {n}",
         "why": "собрано только для лидеров", "fix": "run_youtube_api.py по остальным (~220 ед. квоты на вещь, бесплатно)"},
        {"what": "Подсказки поиска", "have": f"{cnt('ac_modifiers')} из {n}",
         "why": "собрано только для лидеров", "fix": "run_autocomplete.py по остальным (бесплатно)"},
        {"what": "История Amazon", "have": f"{len(amazon_days)} снимка ({', '.join(d[5:] for d in amazon_days)})",
         "why": "2 года продаж и цен есть только в платных сервисах; в веб-архиве хитов Amazon почти нет",
         "fix": "Keepa API (от €49/мес) — когда будем выбирать товар для закупки; пока снимать раз в неделю"},
        {"what": "История брендов", "have": "веб-архив, 2 года" if Path("data/processed/brand_history.csv").exists() else f"{len(brand_days)} снимок",
         "why": "архив хранит страницы новинок раз в месяц; у Free People, Mango, Urban Outfitters копий мало",
         "fix": "run_brand_history.py по команде; живые снимки — run_retailers.py"},
        {"what": "Поиск на Amazon (Trends MCP)", "have": f"{cnt('amazon_monthly_searches')} из {n}",
         "why": "бесплатно только 90 дней и 100 запросов в месяц; редкие фразы сервис не знает",
         "fix": "run_trendsmcp.py по команде; 2 года истории — платный тариф Pro"},
        {"what": "Etsy (микро-ниши)", "have": "заблокирован", "why": "Etsy перевёл ключ в Banned",
         "fix": "новые заявки не подаём — правила Etsy это запрещают"},
        
        
        {"what": "Насыщение рынка", "have": "Amazon, 1-я страница" if Path("data/processed/amazon_saturation.csv").exists() else "нет",
         "why": "видно число товаров, брендов и отзывов; доля рекламы Amazon этому профилю не показывает",
         "fix": "run_saturation.py по команде; позже — TikTok Shop продавцы по кандидату"},
        {"what": "Новые кандидаты", "have": f"{n} слов вручную",
         "why": "радар проверяет только наш список; новые вещи из Pinterest — в разделе «Новые вещи из Pinterest»",
         "fix": "выбрать из раздела Pinterest, кого добавить в кандидаты; дальше — автоподбор из Google rising и брендов"},
        {"what": "Поставщики и маржа", "have": "нет", "why": "намеренно позже — только для прошедших радар",
         "fix": "после выбора вещи для теста"},
    ]


# Pinterest discovery (run_pinterest_discovery.py): every growing term among US women with a garment word.
# kind: item = a concrete thing (her rule «вещь, а не тема»), theme = outfit/ideas/aesthetic/noise.
# season: ours = autumn-winter garment words, off = spring/summer or events, check = decide by the curve.
PIN_THEME = (r"outfit|idea|aesthetic|inspo|look|styl|how to|diy|pattern|crochet|kids|\bmen\b|mens|boy|girl|baby|wedding|party|"
             r"halloween|christmas|photo|pose|hoco|homecoming|school|senior|bleach|frutti|blonde blazer|supreme|silly|funny|yeet|"
             r"vestidos|lab coat|straight jacket|coat of arms|marble hornets|masky|cat in the hat|white lies|danielle|toph|boots with out")
PIN_OURS = (r"coat|trench|jacket|puffer|parka|beanie|scarf|sweater|cardigan|knit|wool|flannel|fleece|fur|suede|leather|corduroy|"
            r"boots|turtleneck|roll neck|plaid|tartan|fall|autumn|winter|hoodie|blazer|vest|leggings")
PIN_OFF = r"capri|shorts|swim|bikini|linen|summer|spring|sundress|prom|rain boots|crop top|tank|halter|beach|sandal"
PIN_PICKS = {"trench coats", "long trench coat", "triangle scarf", "bandana scarf"}  # removed: leather leggings (19% women), pea coat (28+ only 38%)


def pinterest_discovery():
    f = Path("data/processed/pinterest_discovery.csv")
    if not f.exists():
        return [], ""
    df = pd.read_csv(f)
    df["kind"] = df["term"].str.contains(PIN_THEME, case=False, regex=True).map({True: "theme", False: "item"})
    ours = df["term"].str.contains(PIN_OURS, case=False, regex=True)
    off = df["term"].str.contains(PIN_OFF, case=False, regex=True)
    df["season"] = "check"
    df.loc[ours, "season"] = "ours"
    df.loc[off, "season"] = "off"
    df["pick"] = df["term"].isin(PIN_PICKS)
    # 2-year weekly curve + who searches (run_pinterest_extra.py)
    cf, dfile = Path("data/processed/pinterest_discovery_curves.json"), Path("data/processed/pinterest_demographics.csv")
    curves = json.loads(cf.read_text(encoding="utf-8")) if cf.exists() else {}
    df["curve"] = df["term"].map(lambda t: (curves.get(t) or {}).get("values"))
    if dfile.exists():
        demo = pd.read_csv(dfile).drop_duplicates("term").set_index("term")
        df["age"] = df["term"].map(demo["main_age"])
        ages = [c for c in demo.columns if c.startswith("age_")]
        old = [c for c in ages if c not in ("age_18-24", "age_25-34")]
        aud = (0.7 * demo["age_25-34"] + demo[old].sum(axis=1)) / demo[ages].sum(axis=1) * 100
        df["aud28"] = df["term"].map(aud.round())
        # user 23.09.2026: audience from 28; Pinterest skews young for everything -> "young" = below a typical Pinterest item
        df["young"] = df["aud28"] < AUD28_MIN_PINTEREST
        df["female"] = df["term"].map((demo["female"] * 100).round())
        # user 23.09.2026: items whose main audience is 18-24 are removed completely, not just marked
        df = df[df["age"] != "18-24"]
    df = df.sort_values("yoy", ascending=False, na_position="last")
    stamp =datetime.fromtimestamp(f.stat().st_mtime).strftime("%d.%m.%Y")
    return json.loads(df.to_json(orient="records", force_ascii=False)), stamp


FASHION_DATA = Path("C:/Users/User/tg_monitor/fashion_data.json")   # written by tg_monitor/news.py --build


def fashion_section():
    """«Мода — ориентиры»: fashion Telegram channels as a guide for the radar (merged into this page 23.09.2026)."""
    import html as H
    if not FASHION_DATA.exists():
        return ""
    d = json.loads(FASHION_DATA.read_text(encoding="utf-8"))
    a = lambda p: f'<a href="{H.escape(p["link"])}" target="_blank" rel="noopener">{H.escape(p["title"])}</a>'
    themes = "".join(f'<div class="fz-theme"><b>{H.escape(t["theme"])}</b> <span class="mono">{len(t["posts"])} постов</span><br>'
                     + " · ".join(a(p) for p in t["posts"][:5]) + "</div>" for t in d["themes"])
    wa_f = Path("data/processed/word_analysis.csv")
    wa = pd.read_csv(wa_f).set_index("word") if wa_f.exists() else pd.DataFrame()
    cands = set(pd.read_csv("config/candidates.csv")["candidate"])
    cls = {"в кандидаты": "TEST", "наблюдать": "WATCH", "не проходит": "REJECT"}

    rank = {"в кандидаты": 0, "наблюдать": 1, "не проходит": 2}

    def one(word, label=""):
        v = wa.loc[word]
        return (f'{label}<span class="pill {cls.get(v["verdict"], "REJECT")}">{H.escape(v["verdict"])}</span>'
                f'<br><span class="fz-why">{H.escape(str(v["why"]))}</span>')

    def verdict(ph):
        if ph in cands:
            return '<span class="pill TEST">уже кандидат</span>'
        out = one(ph) if ph in wa.index else '<span class="fz-why">ещё не проверено</span>'
        # US wordings of the same item (run_word_analysis.REPHRASE): show the best one
        alts = wa[wa["source"] == f"перефразировка «{ph}»"] if "source" in wa else wa.iloc[0:0]
        if len(alts):
            best = alts.assign(_r=alts["verdict"].map(rank)).sort_values("_r").index[0]
            out += (f'<div class="fz-alt">как ищут в США: <code>{H.escape(best)}</code> — '
                    + one(best).replace("<br>", " ") + "</div>")
        return out
    phrases = "".join(f'<tr><td><code>{H.escape(p["phrase"])}</code></td><td>{verdict(p["phrase"])}</td><td>'
                      + " · ".join(a(x) for x in p["posts"]) + "</td></tr>" for p in d["phrases"])
    cards = ""
    for c in d["cards"]:
        body = "".join(f"<p>{H.escape(x)}</p>" for x in c["summary"])
        if c["for_us"]:
            body += f'<p class="fz-us"><b>Для нас:</b> {H.escape(c["for_us"])}</p>'
        if c["radar"]:
            body += '<p class="fz-us"><b>Проверить в радаре:</b> ' + ", ".join(f"<code>{H.escape(r)}</code>" for r in c["radar"]) + "</p>"
        cards += (f'<article class="fz-card"><div class="fz-meta mono">{H.escape(c["channel"])} · {c["date"]}</div>'
                  f'<h3>{H.escape(c["headline"])}</h3>{body}'
                  f'<a href="{H.escape(c["link"])}" target="_blank" rel="noopener">Открыть пост в Telegram ↗</a></article>')
    return f"""<section id="fashion">
    <h2>Мода — ориентиры из Telegram</h2>
    <p class="note">Новости модных Telegram-каналов — не сами по себе, а как подсказка, какие вещи, цвета и детали проверить здесь
    на спросе в США. Обновлено {H.escape(d["updated"])} (команда «новости»).</p>
    <h3 class="fz-h">Что повторяется <span class="mono">тема в 2+ постах</span></h3>
    <div class="fz-themes">{themes or '<p class="note">Пока ничего не повторяется.</p>'}</div>
    <h3 class="fz-h">Проверить в радаре <span class="mono">{len(d["phrases"])} фраз — каждая проверена; если в США так не ищут, проверена американская формулировка той же вещи (графики — в «Аналитике остальных слов» ниже)</span></h3>
    <div class="tbl-wrap"><table class="fz-ph"><thead><tr><th>Фраза</th><th>Результат проверки</th><th>Откуда</th></tr></thead>{phrases}</table></div>
    <details class="fz-news"><summary>Новости модных каналов ({len(d["cards"])})</summary><div class="fz-cards">{cards}</div></details>
  </section>"""


def words_section():
    """«Аналитика остальных слов» (run_word_analysis.py): fashion phrases + growing Pinterest items run through the
    user's selection rules; a verdict and the reason for every word (user 23.09.2026)."""
    import html as H
    f = Path("data/processed/word_analysis.csv")
    if not f.exists():
        return ""
    df = pd.read_csv(f)
    curves = {}
    for cf in ("data/processed/pinterest_discovery_curves.json", "data/processed/word_analysis_pinterest.json"):
        if Path(cf).exists():
            curves.update(json.loads(Path(cf).read_text(encoding="utf-8")))

    g = pd.read_parquet("data/normalized/google_trends")
    g = g[(g["region"] == "US") & ~g["is_partial"].astype(bool)].sort_values("date").drop_duplicates(["date", "keyword"], keep="last")
    gser = {k: list(x["interest"]) for k, x in g.groupby("keyword")}

    def spark(vals, src=""):
        vals = [v for v in (vals or []) if v is not None]
        if len(vals) < 10 or not any(vals):
            return '<span class="mono" style="color:var(--muted)">нет данных</span>'
        W, Hh, mx, n = 340, 78, max(vals), len(vals)
        pts = " ".join(f"{i / (n - 1) * W:.1f},{Hh - 2 - v / mx * (Hh - 4):.1f}" for i, v in enumerate(vals))
        mid = (n - 52) / (n - 1) * W
        return (f'<svg class="wa-chart" width="{W}" height="{Hh + 14}" viewBox="0 0 {W} {Hh + 14}" role="img" aria-label="{src} за 2 года">'
                f'<line x1="{mid:.1f}" x2="{mid:.1f}" y1="0" y2="{Hh}" stroke="var(--muted)" stroke-dasharray="3 3"/>'
                f'<polyline points="{pts}" fill="none" stroke="var(--bar)" stroke-width="2" stroke-linejoin="round"/>'
                f'<text x="4" y="{Hh + 11}" font-size="10" fill="var(--muted)">{src} · год назад</text>'
                f'<text x="{mid + 4:.1f}" y="{Hh + 11}" font-size="10" fill="var(--muted)">этот год</text></svg>')

    num = lambda v, suf="%": "—" if pd.isna(v) else f'<span class="{"up" if v > 0 else "down" if v < 0 else ""}">{v:+.0f}{suf}</span>'
    cls = {"в кандидаты": "TEST", "наблюдать": "WATCH", "не проходит": "REJECT"}
    rows = ""
    for r in df.itertuples():
        amz = "—" if pd.isna(r.amazon_searches) else f"{int(r.amazon_searches):,}".replace(",", " ")
        rows += (f'<tr><td><b>{H.escape(r.word)}</b><br><span class="mono wa-src">{H.escape(r.source)}</span></td>'
                 f'<td><span class="pill {cls.get(r.verdict, "REJECT")}">{H.escape(r.verdict)}</span></td>'
                 f'<td>{spark((curves.get(r.word) or {}).get("values"), "Pinterest") if any((curves.get(r.word) or {}).get("values") or []) else spark(gser.get(r.word), "Google")}</td>'
                 f'<td class="r">{num(r.pin_yoy)}</td><td class="r">{num(r.google_yoy)}</td>'
                 f'<td>{H.escape(str(r.season)) if pd.notna(r.season) else "—"}</td>'
                 f'<td class="r">{"—" if pd.isna(r.aud28) else f"{r.aud28:.0f}%"}</td>'
                 f'<td class="r">{amz}</td><td class="wa-why">{H.escape(r.why)}</td></tr>')
    n = df["verdict"].value_counts()
    return f"""<section id="words">
    <h2>Аналитика остальных слов</h2>
    <p class="note">Фразы из раздела «Мода — ориентиры» и растущие вещи Pinterest, прогнанные по вашим правилам отбора: рост к году
    (Pinterest; если Pinterest фразу не знает — Google, 8 недель к тем же неделям год назад), сезон осень–зима (по Google),
    аудитория 28+ и женщины, реальный объём (поиск на Amazon в месяц, от 2 000). Только бесплатные источники.
    Итог: <b>в кандидаты — {n.get("в кандидаты", 0)}</b>, наблюдать — {n.get("наблюдать", 0)}, не проходит — {n.get("не проходит", 0)}.
    Добавить в кандидаты радара решаете вы.</p>
    <div class="tbl-wrap"><table class="pd wa">
      <thead><tr><th>Слово</th><th>Итог</th><th>Интерес за 2 года</th><th class="r">Pinterest к году</th><th class="r">Google к году</th>
      <th>Сезон</th><th class="r">28+</th><th class="r">Amazon поиск/мес</th><th>Почему</th></tr></thead>
      <tbody>{rows}</tbody></table></div>
  </section>"""


def variations_section():
    """«Отстройка» (user's method 24.09.2026): mid-frequency variations of each TEST item — colour, cut, fabric —
    with a 2-year Google curve, growth now (Google / Pinterest) and live buying (Amazon «bought», Temu «sold»)."""
    import html as H
    from src.processors.candidate_matrix import months_label, season_calendar, window_stats
    fv, fd = Path("data/processed/variations.csv"), Path("data/processed/variation_demand.csv")
    if not fv.exists():
        return ""
    v = pd.read_csv(fv)
    dem = pd.read_csv(fd).set_index("variation") if fd.exists() else pd.DataFrame()
    # the same variation as a Chinese buyer would type it on 1688 (user 25.09.2026: «на китайском добавляй сразу в дашборд»)
    fq = Path("config/queries_1688.csv")
    zh = dict(pd.read_csv(fq).values) if fq.exists() else {}
    fi = Path("config/items_zh.csv")
    zh_item = dict(pd.read_csv(fi).values) if fi.exists() else {}
    zh_i = lambda it: f' <span class="zh" title="общий запрос для поиска на 1688">{H.escape(zh_item[it])}</span>' if it in zh_item else ""
    zh_cell = lambda var: f'<span class="zh" title="запрос для поиска на 1688">{H.escape(zh[var])}</span>' if var in zh else "—"
    g = pd.read_parquet("data/normalized/google_trends")
    g = g[(g["region"] == "US") & ~g["is_partial"].astype(bool)].sort_values("date").drop_duplicates(["date", "keyword"], keep="last")

    def spark(vals):
        vals = [x for x in vals if x is not None]
        if len(vals) < 10 or not any(vals):
            return '<span class="mono" style="color:var(--muted)">Google: мало данных</span>'
        W, Hh, mx, n = 340, 78, max(vals), len(vals)
        pts = " ".join(f"{i / (n - 1) * W:.1f},{Hh - 2 - x / mx * (Hh - 4):.1f}" for i, x in enumerate(vals))
        mid = (n - 52) / (n - 1) * W
        return (f'<svg class="wa-chart" width="{W}" height="{Hh + 14}" viewBox="0 0 {W} {Hh + 14}" role="img" aria-label="Google за 2 года">'
                f'<line x1="{mid:.1f}" x2="{mid:.1f}" y1="0" y2="{Hh}" stroke="var(--muted)" stroke-dasharray="3 3"/>'
                f'<polyline points="{pts}" fill="none" stroke="var(--bar)" stroke-width="2" stroke-linejoin="round"/>'
                f'<text x="4" y="{Hh + 11}" font-size="10" fill="var(--muted)">Google · год назад</text>'
                f'<text x="{mid + 4:.1f}" y="{Hh + 11}" font-size="10" fill="var(--muted)">этот год</text></svg>')
    num = lambda x: "—" if x is None or pd.isna(x) else f'<span class="{"up" if x > 0 else "down" if x < 0 else ""}">{x:+.0f}%</span>'
    big = lambda x: "—" if x is None or pd.isna(x) else f"{int(x):,}".replace(",", " ")
    out, summary = [], []
    for item, grp in v.groupby("item", sort=False):
        rows = []
        for r in grp.itertuples():
            h = g[g["keyword"] == r.variation]
            vals = list(h["interest"])
            st = window_stats(vals) if len(h) else None
            gy = st["yoy_pct"] if st else None
            season = months_label(season_calendar(list(h["date"]), vals)) if len(h) else ""
            d = dem.loc[r.variation] if r.variation in dem.index else None
            amz = d["amazon_bought_sum"] if d is not None else None
            temu = d["temu_sold"] if d is not None and d["temu_products"] > 0 else None   # 0 products = Temu didn't answer
            grow = any(x is not None and not pd.isna(x) and x >= 5 for x in (gy, r.pin_yoy8w))
            demand = (amz or 0) >= 1000 or (temu or 0) >= 5000
            verdict, cls = (("брать", "TEST") if grow and demand else ("спрос есть, без роста", "WATCH") if demand
                            else ("растёт, покупок мало", "WATCH") if grow else ("не брать", "REJECT"))
            summary.append({"item": item, "var": r.variation, "cls": cls, "verdict": verdict, "gy": gy, "py": r.pin_yoy8w,
                            "amz": amz, "temu": temu})
            rows.append((0 if cls == "TEST" else 1 if cls == "WATCH" else 2, -(amz or 0),
                         f'<tr><td><b>{H.escape(r.variation)}</b><br>{zh_cell(r.variation)}</td><td><span class="pill {cls}">{verdict}</span></td>'
                         f'<td>{spark(vals)}</td><td class="r">{num(gy)}</td><td class="r">{num(r.pin_yoy8w)}</td>'
                         f'<td>{H.escape(season) or "—"}</td><td class="r">{big(amz)}</td>'
                         f'<td class="r">{big(temu) if temu is not None else "нет данных"}</td></tr>'))
        body = "".join(x[2] for x in sorted(rows, key=lambda x: (x[0], x[1])))
        out.append(f'<h3 class="fz-h">{H.escape(item)}{zh_i(item)}</h3><div class="tbl-wrap"><table class="pd wa"><thead><tr>'
                   '<th>Вариация · запрос на 1688</th><th>Вывод</th><th>Интерес за 2 года</th><th class="r">Google к году</th>'
                   '<th class="r">Pinterest к году</th><th>Сезон</th><th class="r">Amazon: куплено за месяц</th>'
                   f'<th class="r">Temu: продано</th></tr></thead><tbody>{body}</tbody></table></div>')
    # summary on top: what to take per item + notable «demand without growth» and «falling» variations
    def g_(x):
        return None if x is None or pd.isna(x) else x
    def fact(x):
        bits = []
        best = max([y for y in (g_(x["gy"]), g_(x["py"])) if y is not None], default=None)
        if best is not None:
            bits.append(f"{best:+.0f}% к году")
        if x["amz"]:
            bits.append(f"Amazon {big(x['amz'])}/мес")
        if x["temu"]:
            bits.append(f"Temu {big(x['temu'])}")
        return ", ".join(bits)
    cards = []
    sm = pd.DataFrame(summary)
    for item, grp in sm.groupby("item", sort=False):
        take = grp[grp["cls"] == "TEST"].sort_values("amz", ascending=False, na_position="last")
        flat = grp[grp["verdict"] == "спрос есть, без роста"].assign(_d=grp["amz"].fillna(0) + grp["temu"].fillna(0) / 20).sort_values("_d", ascending=False)
        fall = grp[grp["gy"].fillna(0) <= -10]
        li = "".join(f"<li><b>{H.escape(x['var'])}</b> {zh_cell(x['var'])} — {fact(x)}</li>" for _, x in take.iterrows()) or "<li>пока ничего</li>"
        notes = ""
        if len(flat):
            notes += "<p class='fz-why'>Покупают много, но роста к году нет: " + ", ".join(
                f"{H.escape(x['var'])} ({fact(x)})" for _, x in flat.head(3).iterrows()) + ".</p>"
        if len(fall):
            notes += "<p class='fz-why'>Падает к прошлому году: " + ", ".join(
                f"{H.escape(x['var'])} ({x['gy']:+.0f}%)" for _, x in fall.iterrows()) + " — не брать как основную вариацию.</p>"
        cards.append(f'<div class="fz-theme"><b>{H.escape(item)}</b>{zh_i(item)} <span class="mono">брать {len(take)} из {len(grp)}</span><ul class="var-take">{li}</ul>{notes}</div>')
    head = f'<h3 class="fz-h">Итог: что брать</h3><div class="fz-themes">{"".join(cards)}</div>'
    return f"""<section id="variations">
    <h2>Отстройка: вариации — цвет, фасон, ткань</h2>
    <p class="note">Ваш метод: от широкого ключа вещи — к среднечастотным вариантам с высоким спросом в моменте и модным фасоном.
    «Брать» — растёт к прошлому году (Google или Pinterest, от 5%) и уже покупают (Amazon от 1 000 в месяц или Temu от 5 000 продаж).
    Под эти вариации подбираем поставщиков и товар. <span class="zh">Китайский текст</span> — готовый запрос для поиска на 1688 (так ищет китайский закупщик);
    добавки: <span class="zh">一件代发</span> — отправка поштучно, <span class="zh">欧美</span>/<span class="zh">跨境</span> — под США.</p>
    {head}
    <h3 class="fz-h">Все вариации с графиками</h3>
    {"".join(out)}
  </section>"""


def main():
    cand = pd.read_csv("data/reports/radar_candidates.csv")
    cand = sort_candidates(cand)   # тест → наблюдать → отказ → короткий сезон
    for col in ["google_yoy_pct", "pin_mom_pct", "pin_yoy_pct", "youtube_yoy_pct"]:
        cand[col] = cand[col].round(0)
    cand["amazon_median_price"] = cand["amazon_median_price"].round(2)
    ac_f = Path("data/processed/autocomplete_summary.csv")
    if ac_f.exists():  # what people type after the item name (Google / YouTube / Amazon)
        ac = pd.read_csv(ac_f)[["candidate", "top_modifiers", "colors", "amazon_examples"]]
        ac = ac.rename(columns={"top_modifiers": "ac_modifiers", "colors": "ac_colors", "amazon_examples": "ac_amazon"})
        cand = cand.merge(ac, on="candidate", how="left")
    zi = Path("config/items_zh.csv")   # общий китайский запрос вещи для 1688 (пользователь 27.09.2026: «добавь сбоку»)
    if zi.exists():
        cand = cand.merge(pd.read_csv(zi), on="candidate", how="left")
    attrs_f = Path("data/processed/retailer_attributes.csv")
    attrs = pd.read_csv(attrs_f) if attrs_f.exists() else pd.DataFrame()
    attrs = attrs[attrs["brands"] >= 2] if not attrs.empty else attrs

    pin_disc, pin_disc_date = pinterest_discovery()
    payload = {
        "date": date.today().strftime("%d.%m.%Y"),
        # exact build time in the header: tells at a glance whether the viewer shows a stale copy
        "updated": datetime.now().strftime("%d.%m.%Y в %H:%M"),
        "channels": CHANNELS,
        "pending": [{"name": n, "why": w} for n, w in PENDING],
        "info": [{"name": n, "note": w} for n, w in INFO_CHANNELS],
        "gaps": data_gaps(cand),
        "candidates": json.loads(cand.to_json(orient="records", force_ascii=False)),
        "attributes": json.loads(attrs.to_json(orient="records", force_ascii=False)) if not attrs.empty else [],
        "pin_discovery": pin_disc,
        "pin_discovery_date": pin_disc_date,
    }
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    curves = build_block(cand, with_header=False, date_str=payload["date"])
    html = TEMPLATE.replace("__FASHION__", variations_section() + fashion_section() + words_section()).replace("__CURVES__", curves).replace("__DATA__", data_json)
    out = Path("data/reports/trend_radar_dashboard.html")
    out.write_text(html, encoding="utf-8")
    print(f"Сохранено: {out} ({len(cand)} кандидатов), обновлено {payload['updated']}")

    update_local(cand, payload["date"], payload["gaps"])
    # --open: show the fresh local copy right away (instant, never a stale cached version)
    if "--open" in sys.argv:
        os.startfile(out.resolve())


def update_local(cand, date_str, gaps=None):
    """Put the curve cards on top of the local Dolphin dashboard, keep the old 12.09 collection below."""
    if not LOCAL.exists():
        print(f"Нет файла {LOCAL} — пропускаю")
        return
    page = LOCAL.read_text(encoding="utf-8")
    block = build_block(cand, with_header=True, date_str=date_str,
                        archive_note="Ниже — архив: сбор 12–13.09 по старой логике (Google Trends 12 мес, TikTok-видео, Instagram).",
                        gaps=gaps)
    start, end = page.find("<!-- RADAR:START"), page.find("<!-- RADAR:END -->")
    if start != -1 and end != -1:
        page = page[:start] + block + page[end + len("<!-- RADAR:END -->\n"):]
    else:
        anchor = '<div class="wrap">'
        i = page.index(anchor) + len(anchor)
        page = page[:i] + "\n" + block + page[i:]
        page = page.replace("<h1>Радар трендов: одежда</h1>",
                            '<h2 style="font-size:22px;margin:6px 0 8px">Архив: радар трендов 12–13.09</h2>', 1)
    LOCAL.write_text(page, encoding="utf-8")
    print(f"Обновлён локальный дашборд: {LOCAL}")


TEMPLATE = r"""<title>Trend Radar</title>
<meta name="description" content="Кандидаты в тренды женской одежды: сколько независимых каналов подтверждают каждый">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Work+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap">
<style>
  :root {
    --page: #f7f6f2; --surface: #ffffff; --surface-2: #efede6;
    --text: #1d1f1a; --text-2: #4b4c45; --muted: #83827a; --border: #e0ddd2;
    --pass: #2f7d5b; --pass-bg: #e3f1ea;
    --fail: #b9b6aa; --fail-bg: #f1efe8;
    --test: #2f7d5b; --test-bg: #e3f1ea;
    --watch: #a0671a; --watch-bg: #f7ecd9;
    --reject: #8a8980; --reject-bg: #efede6;
    --season: #b0472f; --season-bg: #f7e4df;
    --bar: #3f6fa8; --bar-neg: #b0472f;
    color-scheme: light dark;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --page: #151613; --surface: #1f201c; --surface-2: #2a2b26;
      --text: #eceae2; --text-2: #c4c2b6; --muted: #8f8e84; --border: #35362f;
      --pass: #6cc49a; --pass-bg: #1d3329; --fail: #5d5c55; --fail-bg: #262722;
      --test: #6cc49a; --test-bg: #1d3329; --watch: #e0a857; --watch-bg: #3a2d19;
      --reject: #9a998f; --reject-bg: #2a2b26; --season: #e5876f; --season-bg: #3d231c;
      --bar: #7ea7dc; --bar-neg: #e5876f;
    }
  }
  :root[data-theme="dark"] {
    --page: #151613; --surface: #1f201c; --surface-2: #2a2b26;
    --text: #eceae2; --text-2: #c4c2b6; --muted: #8f8e84; --border: #35362f;
    --pass: #6cc49a; --pass-bg: #1d3329; --fail: #5d5c55; --fail-bg: #262722;
    --test: #6cc49a; --test-bg: #1d3329; --watch: #e0a857; --watch-bg: #3a2d19;
    --reject: #9a998f; --reject-bg: #2a2b26; --season: #e5876f; --season-bg: #3d231c;
    --bar: #7ea7dc; --bar-neg: #e5876f;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--page); color: var(--text);
         font-family: "Work Sans", system-ui, sans-serif; font-size: 14.5px; line-height: 1.5; }
  .wrap { max-width: 1280px; margin: 0 auto; padding-inline: 20px; padding-block: 28px 72px; }
  .updated { margin: 10px 0 0; font-size: 13px; color: var(--muted); }
  .updated b { color: var(--text); font-size: 14px; background: var(--surface); border: 1px solid var(--border);
               border-radius: 8px; padding: 2px 8px; }
  details.howto { margin-top: 14px; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 10px 16px; }
  details.howto summary { display: list-item; list-style: disclosure-closed; padding: 0; cursor: pointer;
                          font-weight: 600; font-size: 13.5px; color: var(--text-2); }
  details.howto[open] summary { list-style: disclosure-open; }
  details.howto[open] summary { margin-bottom: 8px; }
  section.cands { margin-top: 18px; }
  h1, h2 { font-family: "Fraunces", Georgia, serif; margin: 0; text-wrap: balance; }
  h1 { font-size: 30px; }
  h2 { font-size: 20px; margin-bottom: 4px; }
  .mono { font-family: "JetBrains Mono", ui-monospace, monospace; }
  .eyebrow { font: 600 11px "JetBrains Mono", monospace; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
  .lead { color: var(--text-2); max-width: 66ch; margin: 8px 0 0; }
  section { margin-top: 36px; }
  .note { color: var(--muted); font-size: 13px; margin: 0 0 14px; max-width: 70ch; }

  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-top: 20px; }
  .stat { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; }
  .stat .n { font: 700 24px "Fraunces", serif; font-variant-numeric: tabular-nums; }
  .stat .l { font-size: 12px; color: var(--muted); }

  .rule { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; font-size: 13px; color: var(--text-2); }
  .rule span { background: var(--surface); border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px; }

  .filters { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
  .filters button { font: 600 12.5px "Work Sans", sans-serif; color: var(--text-2); background: var(--surface);
                    border: 1px solid var(--border); border-radius: 999px; padding: 6px 14px; cursor: pointer; min-height: 34px; }
  .filters button[aria-pressed="true"] { background: var(--text); color: var(--page); border-color: var(--text); }
  .filters button:focus-visible, summary:focus-visible { outline: 2px solid var(--bar); outline-offset: 2px; }

  .list { display: flex; flex-direction: column; gap: 8px; }
  details.row { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; }
  details.row.test { border-color: var(--test); box-shadow: 0 0 0 1px var(--test) inset; }
  summary { list-style: none; cursor: pointer; padding: 12px 16px;
            display: grid; grid-template-columns: minmax(150px, 1.6fr) auto auto minmax(110px, 1fr); gap: 14px; align-items: center; }
  summary::-webkit-details-marker { display: none; }
  summary > * { min-width: 0; }
  .name small { overflow-wrap: anywhere; }
  .name { font-weight: 600; }
  .name small { display: block; font-weight: 400; color: var(--muted); font-size: 12px; }
  .checks { display: flex; gap: 4px; }
  .chk { width: 26px; height: 26px; border-radius: 7px; display: grid; place-items: center;
         font: 600 11px "JetBrains Mono", monospace; }
  .chk.on { background: var(--pass-bg); color: var(--pass); }
  .chk.off { background: var(--fail-bg); color: var(--fail); }
  .pill { font: 600 11.5px "JetBrains Mono", monospace; padding: 4px 10px; border-radius: 999px; white-space: nowrap; }
  .pill.TEST { background: var(--test-bg); color: var(--test); }
  .pill.WATCH { background: var(--watch-bg); color: var(--watch); }
  .pill.STEADY { background: var(--bar); color: var(--page); }
  .pill.REJECT { background: var(--reject-bg); color: var(--reject); }
  .pill.season { background: var(--season-bg); color: var(--season); margin-left: 6px; }
  .yoy { display: flex; align-items: center; gap: 8px; font-size: 12.5px; font-variant-numeric: tabular-nums; }
  .yoy .track { flex: 1; height: 8px; background: var(--surface-2); border-radius: 4px; position: relative; min-width: 60px; }
  .yoy .zero { position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--muted); }
  .yoy .fill { position: absolute; top: 0; bottom: 0; border-radius: 4px; }
  .why { margin: 0 16px 10px; font-size: 13px; color: var(--season); background: var(--season-bg);
         border-radius: 8px; padding: 6px 10px; }
  .evidence { padding: 0 16px 14px; display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }
  .ev { background: var(--page); border-radius: 10px; padding: 10px 12px; font-size: 13px; }
  .ev b { display: block; font-size: 11px; font-family: "JetBrains Mono", monospace; letter-spacing: .05em;
          text-transform: uppercase; color: var(--muted); margin-bottom: 3px; }
  .ev .no { color: var(--muted); }

  .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
  .ch { display: flex; gap: 10px; align-items: flex-start; padding: 8px 0; border-top: 1px solid var(--border); }
  .ch:first-of-type { border-top: 0; }
  .dot { width: 9px; height: 9px; border-radius: 50%; margin-top: 6px; flex-shrink: 0; }
  .dot.ok { background: var(--pass); } .dot.partial { background: var(--watch); } .dot.wait { background: var(--fail); }
  .ch small { display: block; color: var(--muted); font-size: 12px; }
  .attr { display: flex; justify-content: space-between; gap: 10px; padding: 7px 0; border-top: 1px solid var(--border); font-size: 13.5px; }
  .attr:first-of-type { border-top: 0; }
  .attr .b { color: var(--muted); font-size: 12px; text-align: right; }
  .gaps { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; }
  .gap { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px;
         display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
  .gap-head { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
  .gap-head b { font-size: 14px; }
  .gap-have { font: 600 11.5px "JetBrains Mono", monospace; color: var(--watch); white-space: nowrap; }
  .gap-why { color: var(--text-2); }
  .gap-fix { color: var(--muted); }
  .gap-fix::before { content: "→ "; }

  .tbl-wrap { overflow-x: auto; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; max-height: 1100px; overflow-y: auto; }
  table.pd { width: 100%; border-collapse: collapse; font-size: 13.5px; }
  table.pd th { position: sticky; top: 0; background: var(--surface-2); text-align: left; font: 600 11.5px "JetBrains Mono", monospace;
                color: var(--text-2); padding: 8px 12px; cursor: pointer; white-space: nowrap; user-select: none; }
  table.pd td { padding: 5px 12px; vertical-align: middle; border-top: 1px solid var(--border); white-space: nowrap; }
  table.pd .r { text-align: right; font-variant-numeric: tabular-nums; font-family: "JetBrains Mono", monospace; font-size: 12.5px; }
  table.pd tr.pick td:first-child { font-weight: 700; }
  table.pd tr.pick td:first-child::before { content: "★ "; color: var(--watch); }
  table.pd tr.theme td:first-child { color: var(--muted); }
  .up { color: var(--pass); } .down { color: var(--bar-neg); }
  .sz { font: 600 11px "JetBrains Mono", monospace; padding: 2px 8px; border-radius: 999px; }
  .sz.ours { background: var(--test-bg); color: var(--test); }
  .sz.off { background: var(--reject-bg); color: var(--reject); }
  .sz.check { background: var(--watch-bg); color: var(--watch); }
  .fz-h { font: 600 15px "Work Sans", sans-serif; margin: 18px 0 8px; }
  .fz-h .mono { font-size: 11px; color: var(--muted); font-weight: 500; }
  .fz-themes { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 8px; }
  .fz-theme { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 10px 14px; font-size: 13px; }
  .fz-theme b { font-size: 15px; }
  .fz-theme .mono { font-size: 11px; color: var(--muted); }
  table.fz-ph { width: 100%; border-collapse: collapse; font-size: 13px; }
  table.fz-ph td { padding: 7px 12px; border-top: 1px solid var(--border); vertical-align: top; }
  details.fz-news { margin-top: 14px; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 10px 16px; }
  details.fz-news summary { display: list-item; list-style: disclosure-closed; padding: 0; font-weight: 600; cursor: pointer; }
  details.fz-news[open] summary { list-style: disclosure-open; margin-bottom: 10px; }
  .fz-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr)); gap: 10px; }
  .fz-card { background: var(--page); border-radius: 12px; padding: 12px 14px; font-size: 13px; }
  .fz-card h3 { font: 700 14.5px "Work Sans", sans-serif; margin: 4px 0 6px; }
  .fz-card p { margin: 0 0 6px; color: var(--text-2); }
  .fz-meta { font-size: 11px; color: var(--muted); }
  .fz-us { border-left: 3px solid var(--pass-bg); padding-left: 8px; }
  table.wa td { white-space: normal; vertical-align: middle; }
  table.wa td:first-child { min-width: 170px; }
  .fz-why { font-size: 11.5px; color: var(--muted); }
  .fz-alt { margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--border); font-size: 12px; }
  table.fz-ph th { text-align: left; font: 600 11px "JetBrains Mono", monospace; color: var(--text-2); padding: 7px 12px; background: var(--surface-2); }
  .wa-chart { display: block; }
  .var-take { margin: 6px 0; padding-left: 18px; }
  .var-take li { margin: 2px 0; }
  .zh { font-family: 'Noto Sans SC', 'Microsoft YaHei', 'PingFang SC', sans-serif; font-size: 12.5px; color: var(--text); background: var(--chip, rgba(127,127,127,.12)); padding: 1px 6px; border-radius: 4px; user-select: all; white-space: nowrap; }
  .wa-src { font-size: 10.5px; color: var(--muted); }
  .wa-why { font-size: 12.5px; color: var(--text-2); min-width: 220px; }
  table.wa .pill { white-space: nowrap; }
  @media (max-width: 640px) {
    summary { grid-template-columns: 1fr auto; }
    .yoy { grid-column: 1 / -1; }
  }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="wrap">
  <div class="eyebrow">Trend Radar · женская одежда · США</div>
  <h1>Какие вещи подтверждают сразу несколько каналов</h1>
  <p class="lead">Один сигнал — это шум. Радар проверяет каждого кандидата независимыми «свидетелями» и считает, сколько из них видят рост.</p>
  <p class="updated">Обновлено <b class="mono" id="dt"></b> — если здесь старое время, нажмите F5</p>
  <p class="updated"><a href="#variations">Отстройка: вариации ↓</a> · <a href="#fashion">Мода — ориентиры из Telegram ↓</a> · <a href="#words">Аналитика остальных слов ↓</a></p>
  <div class="stats" id="stats"></div>
  <details class="howto">
  <summary>Как читать радар: правила решений и буквы каналов</summary>
  <div class="rule">
    <span><b>5–7 проверок</b> — тестировать</span>
    <span><b>3–4</b> — наблюдать; также наблюдать, если роста к прошлому году нет, но спрос большой и не падает (от 5 тыс. поисков на Amazon в месяц, 5+ товаров в хитах или от 1000 покупок за месяц на первой странице поиска Amazon)</span>
    <span><b>0–2</b> — отказ</span>
    <span><b>Сезон</b> — в эти же недели прошлого года был такой же подъём</span>
    <span><b>Короткий сезон</b> — спрос держится меньше 2 месяцев: отказ в любом случае</span>
    <span><b>Не наш сезон — отказ</b>: мы продаём только на осень–зиму (сен–фев); если сезон вещи (по Google Trends) в эти месяцы не попадает, её не рассматриваем</span>
    <span><b>Аудитория от 28 лет</b>: если больше половины интереса у людей младше 28 (по Google; нет Google — по Pinterest), вещь — отказ</span>
    <span><b>Сезон вот-вот начнётся</b> — год назад в следующие 8 недель интерес рос на 20%+ (по Google Trends), а в этом году не ниже прошлого: наблюдать обязательно</span>
    <span><b>Только стабильный рост</b> — по Pinterest последние 8 недель и 3 из 4 кварталов выше прошлого года на 5%+</span>
  </div>
  <p class="note">Порядок: тестировать, наблюдать, позже, отказы, в самом конце — короткие сезоны. Буквы: G — Google (обычный поиск), P — Pinterest, Y — поиск на YouTube (у всех трёх: последние 8 недель выше тех же недель прошлого года на 5%+), T — TikTok (хэштег в топе или рост за 2 недели на 5%+), A — Amazon (≥2 товара в хитах или поиск за месяц вырос на 5%+), R — бренды (≥2 ритейлера), I — Instagram (≥1 пост в день под хэштегом). На графиках вся кривая за 2 года; радар сравнивает последние 8 недель с теми же неделями год назад. Горб справа выше прошлогоднего — настоящий рост; одинаковые — просто сезон. Шкала 0–100, где 100 — пик за 2 года.</p>
  </details>

  <section class="cands">
    __CURVES__
    <div class="list" id="list" hidden></div>
  </section>

  __FASHION__

  <section id="pin-disc">
    <h2>Новые вещи из Pinterest</h2>
    <p class="note">Растущие запросы Pinterest среди женщин в США, в которых есть название вещи (свитер, юбка, пальто…). Вещи, которыми больше всего интересуются 18–24-летние, убраны совсем (решение 23.09: не наша аудитория). Собрано через бизнес-вход в Pinterest Trends <span class="mono" id="pd-date"></span>. Рост — по сравнению с неделей, месяцем и годом раньше; «спрос» — индекс Pinterest (больше — чаще ищут). «28+» — доля интереса от людей 28 лет и старше; красным — аудитория моложе, чем у типичной вещи Pinterest (Pinterest в целом молодой: обычно 43–51%). Звёздочка — мой совет добавить в кандидаты; решение за вами.</p>
    <div class="filters" id="pd-filters">
      <button data-f="ours" aria-pressed="true">Наш сезон и аудитория 28+, растут к году</button>
      <button data-f="items" aria-pressed="false">Все вещи с ростом к году</button>
      <button data-f="all" aria-pressed="false">Все запросы</button>
    </div>
    <div class="tbl-wrap"><table class="pd">
      <thead><tr>
        <th data-k="term">Запрос</th><th data-k="season">Сезон</th><th>2 года</th><th data-k="age">Чаще всего</th><th data-k="aud28" class="r">28+</th>
        <th data-k="female" class="r">Женщин</th><th data-k="wow" class="r">Неделя</th>
        <th data-k="mom" class="r">Месяц</th><th data-k="yoy" class="r">Год ▾</th><th data-k="volume_idx" class="r">Спрос</th>
        <th data-k="list">Список</th></tr></thead>
      <tbody id="pd-body"></tbody>
    </table></div>
    <p class="note" id="pd-count"></p>
  </section>

  <section class="grid2">
    <div>
      <h2>Каналы</h2>
      <p class="note">Что радар уже слушает и чего пока не хватает.</p>
      <div class="card" id="channels"></div>
    </div>
    <div>
      <h2>Что выпускают бренды</h2>
      <p class="note">Признаки, которые есть в новинках сразу у нескольких ритейлеров.</p>
      <div class="card" id="attrs"></div>
    </div>
  </section>

  <section>
    <h2>Чего не хватает радару</h2>
    <p class="note">Что ещё не собирается или собрано не по всем кандидатам. Цифры пересчитываются при каждой сборке страницы.</p>
    <div class="gaps" id="gaps"></div>
  </section>
</div>

<script id="radar-data" type="application/json">__DATA__</script>
<script>
(() => {
  const D = JSON.parse(document.getElementById("radar-data").textContent);
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const DEC = { TEST: "тестировать", WATCH: "наблюдать", LATER: "позже", REJECT: "отказ" };
  const GROUP = { material: "ткань", pattern: "принт", neckline: "ворот", silhouette: "силуэт", detail: "деталь", audience_occasion: "аудитория" };
  const ATTR = { knit: "трикотаж", oversized: "оверсайз", plaid: "клетка", roll_neck: "высокий ворот", stripe: "полоска",
                 faux_fur: "искусственный мех", v_neck: "V-вырез", leather: "кожа", wool: "шерсть", boat_neck: "лодочка",
                 maxi: "макси", lace: "кружево", cashmere: "кашемир", mesh: "сетка", drawstring: "кулиска",
                 plus_size: "plus size", ruffle: "рюши", bow: "бант", satin: "атлас", suede: "замша", sequin: "пайетки",
                 flannel: "фланель", leopard: "леопард", floral: "цветы", ribbed: "рубчик", denim: "деним", halter: "халтер" };

  $("dt").textContent = D.updated || D.date;
  const c = D.candidates, n = (d) => c.filter((x) => x.decision === d).length;
  $("stats").innerHTML = [
    [c.length, "кандидатов проверено"], [n("TEST"), "тестировать"], [n("WATCH"), "наблюдать"],
    [D.channels.length, "каналов подключено"],
  ].map(([v, l]) => `<div class="stat"><div class="n">${v}</div><div class="l">${l}</div></div>`).join("");

  const pct = (v) => v === null || v === undefined ? null : Number(v);
  const yoyBar = (v) => {
    if (v === null) return `<div class="yoy"><span class="mono" style="color:var(--muted)">нет на Pinterest</span></div>`;
    const w = Math.min(Math.abs(v), 100) / 2;
    const left = v >= 0 ? 50 : 50 - w;
    const col = v >= 0 ? "var(--bar)" : "var(--bar-neg)";
    return `<div class="yoy"><div class="track"><div class="zero"></div><div class="fill" style="left:${left}%;width:${w}%;background:${col}"></div></div><span class="mono">${v > 0 ? "+" : ""}${v}%</span></div>`;
  };
  const ev = (label, body) => `<div class="ev"><b>${label}</b>${body || '<span class="no">нет сигнала</span>'}</div>`;

  function render(filter) {
    $("list").innerHTML = c.filter((x) => filter === "ALL" || x.decision === filter).map((x) => {
      const chips = D.channels.map((ch) => `<span class="chk ${x[ch.key] ? "on" : "off"}" title="${ch.name}: ${x[ch.key] ? "да" : "нет"}">${ch.short}</span>`).join("");
      const y = pct(x.pin_yoy_pct), m = pct(x.pin_mom_pct);
      const g = [x.google_rising_top, x.google_yoy_pct !== null && x.google_yoy_pct !== undefined ? `8 недель к прошлому году: ${x.google_yoy_pct > 0 ? "+" : ""}${x.google_yoy_pct}%` : ""].filter(Boolean).map(esc).join("<br>");
      const lift = x.pin_season_lift_prev;
      const p = m === null && y === null ? "" : `за месяц ${m > 0 ? "+" : ""}${m ?? "—"}% · 8 недель к прошлому году ${y > 0 ? "+" : ""}${y ?? "—"}%`
        + (lift !== null && lift !== undefined ? `<br>год назад в эти недели: ${lift > 0 ? "+" : ""}${Math.round(lift)}%` : "");
      const sgn = (v) => `${v > 0 ? "+" : ""}${Math.round(v)}%`;
      const vol = (v) => v >= 1000 ? `${Math.round(v / 1000)} тыс.` : String(v);
      const a = [
        x.amazon_items ? `${x.amazon_items} товаров (новинок ${x.amazon_new_releases}), медиана $${x.amazon_median_price}` : "",
        x.amazon_monthly_searches ? `искали ${vol(x.amazon_monthly_searches)} раз за месяц, ${sgn(x.amazon_mcp_lift_pct)} к прошлому месяцу` : ""
      ].filter(Boolean).join("<br>");
      const t = [esc(x.tiktok_hashtags),
        x.tiktok_mcp_lift_pct !== null && x.tiktok_mcp_lift_pct !== undefined ? `объём хэштега за 2 недели: ${sgn(x.tiktok_mcp_lift_pct)}` : ""
      ].filter(Boolean).join("<br>");
      const amz = x.amazon_monthly_searches ? ` · Amazon ${vol(x.amazon_monthly_searches)} поисков/мес` : "";
      return `<details class="row ${x.decision === "TEST" ? "test" : ""}">
        <summary>
          <div class="name">${esc(x.candidate)}${x.zh ? ` <span class="zh" title="общий запрос для поиска на 1688">${esc(x.zh)}</span>` : ""}<small>${x.checks_passed} из ${D.channels.length} проверок${x.season_weeks ? ` · сезон ${x.season_weeks >= 52 ? "круглый год" : Math.round(x.season_weeks) + " нед"}` : ""}${amz}</small></div>
          <div class="checks">${chips}</div>
          <div><span class="pill ${x.decision}">${DEC[x.decision]}</span>${x.short_season ? '<span class="pill season">короткий сезон</span>' : x.seasonal_flag ? '<span class="pill season">сезон</span>' : ""}</div>
          ${yoyBar(y)}
        </summary>
        ${x.reject_reason ? `<div class="why">Почему отказ: ${esc(x.reject_reason)}${x.pin_quarters ? ` · Pinterest по кварталам: ${esc(x.pin_quarters)}` : ""}</div>` : ""}
        <div class="evidence">
          ${ev("Google", g)}${ev("Pinterest", p)}${ev("YouTube", [
            x.youtube_yoy_pct === null || x.youtube_yoy_pct === undefined ? "" : `поиск, 8 недель к прошлому году: ${x.youtube_yoy_pct > 0 ? "+" : ""}${x.youtube_yoy_pct}%`,
            x.yt_views_yoy_pct === null || x.yt_views_yoy_pct === undefined ? "" : `просмотры видео за 90 дн: ${x.yt_views_yoy_pct > 0 ? "+" : ""}${Math.round(x.yt_views_yoy_pct)}% к прошлому году`,
            x.yt_comments_read ? `«где купить»: ${x.yt_intent_comments} из ${x.yt_comments_read} комментариев` : ""
          ].filter(Boolean).join("<br>"))}${ev("TikTok", t)}
          ${ev("Amazon", a)}${ev("Бренды", x.retailer_brands ? `${x.retailer_brands}: ${esc(x.retailer_list)}` : "")}
        </div>
      </details>`;
    }).join("") || '<p class="note">Нет кандидатов в этой группе.</p>';
  }
  render("ALL");
  document.querySelectorAll(".filters button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".filters button").forEach((o) => o.setAttribute("aria-pressed", String(o === b)));
    render(b.dataset.f);
  }));

  // Pinterest discovery table: filter buttons + click-to-sort headers
  const PD = D.pin_discovery || [];
  const SZ = { ours: "осень–зима", off: "не наш", check: "проверить" };
  const LST = { growing: "растущие", seasonal: "сезонные" };
  let pdFilter = "ours", pdKey = "yoy", pdDir = -1;
  const num = (v) => v === null || v === undefined ? "—" : `<span class="${v > 0 ? "up" : v < 0 ? "down" : ""}">${v > 0 ? "+" : ""}${v >= 10000 ? "10000%+" : v + "%"}</span>`;
  // 2-year weekly Pinterest curve as a small line; the year boundary is marked so last year's bump is comparable
  const spark = (v) => {
    if (!v || v.length < 10) return '<span style="color:var(--muted)">—</span>';
    const W = 300, H = 60, mx = Math.max(...v, 1), n = v.length;
    const pts = v.map((y, i) => `${(i / (n - 1) * W).toFixed(1)},${(H - 2 - y / mx * (H - 4)).toFixed(1)}`).join(" ");
    const mid = (n - 52) / (n - 1) * W;
    return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="кривая за 2 года">
      <line x1="${mid}" x2="${mid}" y1="0" y2="${H}" stroke="var(--muted)" stroke-dasharray="3 3"/>
      <polyline points="${pts}" fill="none" stroke="var(--bar)" stroke-width="2" stroke-linejoin="round"/></svg>`;
  };
  function renderPD() {
    const rows = PD.filter((r) => pdFilter === "all" || (r.kind === "item" && (r.yoy ?? 0) >= 5 && (pdFilter === "items" || (r.season === "ours" && !r.young))))
      .sort((a, b) => { const x = a[pdKey], y = b[pdKey]; return (typeof x === "string" ? String(x).localeCompare(y) : (x ?? -1e9) - (y ?? -1e9)) * pdDir; });
    $("pd-body").innerHTML = rows.map((r) => `<tr class="${r.pick ? "pick" : ""} ${r.kind === "theme" ? "theme" : ""}">
      <td>${esc(r.term)}</td><td><span class="sz ${r.season}">${SZ[r.season]}</span></td>
      <td>${spark(r.curve)}</td><td>${r.age ? esc(r.age) : "—"}</td><td class="r"><span class="${r.young ? "down" : r.aud28 != null ? "up" : ""}">${r.aud28 != null ? r.aud28 + "%" : "—"}</span></td><td class="r">${r.female != null ? r.female + "%" : "—"}</td>
      <td class="r">${num(r.wow)}</td><td class="r">${num(r.mom)}</td><td class="r">${num(r.yoy)}</td>
      <td class="r">${r.volume_idx ?? "—"}</td><td>${LST[r.list] || r.list}</td></tr>`).join("")
      || '<tr><td colspan="11">Нет данных — запустите run_pinterest_discovery.py</td></tr>';
    $("pd-count").textContent = `Показано ${rows.length} из ${PD.length} запросов.`;
  }
  $("pd-date").textContent = D.pin_discovery_date ? `(${D.pin_discovery_date})` : "";
  document.querySelectorAll("#pd-filters button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("#pd-filters button").forEach((o) => o.setAttribute("aria-pressed", String(o === b)));
    pdFilter = b.dataset.f; renderPD();
  }));
  document.querySelectorAll("table.pd th").forEach((th) => th.addEventListener("click", () => {
    const k = th.dataset.k; pdDir = pdKey === k ? -pdDir : (["term", "season", "list"].includes(k) ? 1 : -1); pdKey = k;
    document.querySelectorAll("table.pd th").forEach((o) => o.textContent = o.textContent.replace(/ [▾▴]$/, ""));
    th.textContent += pdDir < 0 ? " ▾" : " ▴"; renderPD();
  }));
  renderPD();

  $("channels").innerHTML =
    D.channels.map((ch) => `<div class="ch"><span class="dot ${ch.status}"></span><div><b>${ch.name}</b><small>${esc(ch.note)}</small></div></div>`).join("") +
    (D.info || []).map((c) => `<div class="ch"><span class="dot ok"></span><div><b>${c.name}</b> <small style="display:inline">(в карточках, не голос)</small><small>${esc(c.note)}</small></div></div>`).join("") +
    D.pending.map((p) => `<div class="ch"><span class="dot wait"></span><div><b>${p.name}</b><small>не подключено — ${esc(p.why)}</small></div></div>`).join("");

  $("gaps").innerHTML = (D.gaps || []).map((g) => `<div class="gap">
      <div class="gap-head"><b>${esc(g.what)}</b><span class="gap-have">${esc(g.have)}</span></div>
      <div class="gap-why">${esc(g.why)}</div><div class="gap-fix">${esc(g.fix)}</div></div>`).join("");

  $("attrs").innerHTML = D.attributes.length ? D.attributes.map((a) =>
    `<div class="attr"><span>${ATTR[a.attribute] || esc(a.attribute)} <span style="color:var(--muted)">· ${GROUP[a.group] || a.group}</span></span><span class="b">${a.brands} бренда · ${a.items} шт</span></div>`).join("")
    : '<p class="note">Нет данных.</p>';
})();
</script>
"""

if __name__ == "__main__":
    main()
