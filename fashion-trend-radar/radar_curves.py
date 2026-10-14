"""
Curve cards for every radar candidate: this year's weekly interest vs the same
weeks a year ago (Pinterest, and Google where 2-year history exists).
build_block() returns a self-contained HTML fragment (style + markup + script)
that works inside both dashboards -- colours come from the host page tokens.
"""
import html
import json
from pathlib import Path

import pandas as pd

from src.processors.candidate_matrix import MIN_NONZERO

WEEKS = 52


def pinterest_aliases() -> dict:
    """candidate -> wording Pinterest Trends knows (config/candidates.csv, column pinterest_term)."""
    c = pd.read_csv("config/candidates.csv")
    if "pinterest_term" not in c:
        return {}
    return {r.candidate: r.pinterest_term for r in c.itertuples() if isinstance(r.pinterest_term, str) and r.pinterest_term}


def use_short_phrase(hist: pd.DataFrame, min_weeks: int = 3) -> pd.DataFrame:
    """Google/YouTube history: a candidate whose own phrase is almost never searched (< min_weeks non-zero US weeks)
    gets the curve of its shorter wording (pinterest_term, e.g. flannel shirt women -> flannel shirt)."""
    if hist.empty:
        return hist
    us = hist[hist["region"] == "US"]
    alive = lambda k: int((us[us["keyword"] == k]["interest"] > 0).sum()) >= min_weeks
    extra = []
    for cand, short in pinterest_aliases().items():
        if not alive(cand) and alive(short):
            extra.append(hist[hist["keyword"] == short].assign(keyword=cand))
    if not extra:
        return hist
    return pd.concat([hist[~hist["keyword"].isin([e["keyword"].iloc[0] for e in extra])]] + extra, ignore_index=True)


def _pinterest_series():
    """term -> weekly points, keyed by CANDIDATE: latest metrics_*.json plus variants_*.json
    (other wordings, run_extra_signals.py); a candidate with an alias gets its alias's curve."""
    root = Path("data/raw/pinterest_trends")
    files = sorted(root.glob("metrics_*.json"))[-1:] + sorted(root.glob("variants_*.json"))
    out = {}
    for f in files:   # later files win
        for batch in json.loads(f.read_text(encoding="utf-8")).values():
            for t in batch:
                if not t:
                    continue
                pts = [(c["date"], c["normalizedCount"]) for c in t.get("counts", [])
                       if c.get("normalizedCount") is not None]
                out[t["term"]] = pts
    for cand, alias in pinterest_aliases().items():
        if alias in out:
            out[cand] = out[alias]
    return out


def _google_series(root="data/normalized/google_trends"):
    root = Path(root)
    if not root.exists():
        return {}
    g = pd.read_parquet(root).sort_values("date").drop_duplicates(["date", "keyword", "region"], keep="last")
    g = use_short_phrase(g)
    g = g[(g["region"] == "US") & ~g["is_partial"].astype(bool)]
    out = {}
    for k, grp in g.groupby("keyword"):
        if grp["interest"].max() > 0:   # all zeros = too few searches to draw anything
            out[k] = [(str(d)[:10], float(v)) for d, v in zip(grp["date"], grp["interest"])]
    return out


def _amazon_months():
    """candidate -> [{label, v}] monthly Amazon searches (trendsmcp raw answers, newest file per candidate)."""
    out = {}
    raw = Path("data/raw/trendsmcp")
    if not raw.exists():
        return out
    from src.processors.candidate_matrix import AMAZON_SEARCH_ALIAS
    for c in pd.read_csv("config/candidates.csv")["candidate"]:
        # the exact phrase first; if Trends MCP doesn't know it — the closest phrase (same as the radar uses)
        for phrase in [c] + ([AMAZON_SEARCH_ALIAS[c]] if c in AMAZON_SEARCH_ALIAS else []):
            files = sorted(raw.glob(f"*_get_time_series_amazon_{phrase.replace(' ', '-')}.json"))
            if not files:
                continue
            d = json.loads(files[-1].read_text(encoding="utf-8"))
            body = d.get("body") if isinstance(d, dict) else None
            rows = json.loads(body) if isinstance(body, str) else (d if isinstance(d, list) else [])
            if not isinstance(rows, list):   # {"error": "no_data", ...}
                continue
            pts = [(r["date"], r.get("volume")) for r in rows if isinstance(r, dict) and r.get("volume") is not None]
            if pts:
                pts = sorted(pts)
                stale = pd.Timestamp(pts[-1][0]) < pd.Timestamp.today() - pd.Timedelta(days=62)
                out[c] = [{"label": f"{MONTHS[int(dt[5:7]) - 1]} {dt[2:4]}" + (" (устарело)" if stale and i == len(pts) - 1 else ""),
                           "v": int(v)} for i, (dt, v) in enumerate(pts)]
                break
    return out


def _tiktok_weeks(weeks=12):
    """candidate -> [{label, v}] new US videos under our hashtag per week, last `weeks` weeks (Monday-based)."""
    from datetime import date, timedelta
    f = Path("data/processed/tiktok_tag_videos.csv")
    if not f.exists():
        return {}
    v = pd.read_csv(f)
    v = v[v["region"].fillna("US") == "US"].copy()
    v["created"] = pd.to_datetime(v["created"], errors="coerce")
    monday = date.today() - timedelta(days=date.today().weekday())
    starts = [monday - timedelta(weeks=k) for k in range(weeks - 1, -1, -1)]
    out = {}
    for c, g in v.groupby("candidate"):
        days = g["created"].dt.date
        out[c] = [{"label": f"{s.day} {MONTHS[s.month - 1]}", "v": int(((days >= s) & (days < s + timedelta(days=7))).sum())}
                  for s in starts]
    return out


def _instagram():
    """candidate -> {per_day, sampled, oldest, likes_median, top:[{link, likes, date}]}"""
    f, fp = Path("data/processed/instagram_tags.csv"), Path("data/processed/instagram_tag_posts.csv")
    if not f.exists():
        return {}
    s = pd.read_csv(f).set_index("candidate")
    posts = pd.read_csv(fp) if fp.exists() else pd.DataFrame()
    out = {}
    for c, r in s.iterrows():
        top = []
        if not posts.empty:
            g = posts[posts["candidate"] == c].sort_values("likes", ascending=False).head(3)
            top = [{"link": x.link, "likes": int(x.likes or 0), "date": str(x.taken_at)[:10]} for x in g.itertuples()]
        out[c] = {"tag": r["hashtag"], "per_day": None if pd.isna(r["posts_per_day"]) else float(r["posts_per_day"]),
                  "sampled": int(r["posts_sampled"]), "oldest": str(r["oldest"]),
                  "likes_median": None if pd.isna(r["likes_median"]) else int(r["likes_median"]), "top": top,
                  "sample": r["sample"] if "sample" in r and isinstance(r["sample"], str) else "recent"}
    return out


def _google_volume():
    """candidate -> {"months": [{label, v}], avg, last, last_vs_avg, cpc} real US Google searches (DataForSEO)."""
    f, fm = Path("data/processed/google_volume.csv"), Path("data/processed/google_volume_monthly.csv")
    if not f.exists() or not fm.exists():
        return {}
    s, m = pd.read_csv(f).set_index("candidate"), pd.read_csv(fm)
    weekly = _google_series()   # Google Trends 0-100 by week, for the current-month estimate
    out = {}
    for c, g in m.sort_values("month").groupby("candidate"):
        r = s.loc[c] if c in s.index else None
        months = [{"label": MONTHS[int(x[5:7]) - 1] + ("’" + x[2:4] if x[5:7] == "01" else ""), "v": int(v or 0)}
                  for x, v in zip(g["month"], g["searches"])]
        # Monthly volumes come only for finished months. Estimate the running month:
        # last full month's volume x (this month's full weeks / last month's weeks) in Google Trends.
        last_m = g["month"].iloc[-1]
        nxt = pd.Period(last_m, "M") + 1
        wk = weekly.get(c) or []
        cur = [v for d, v in wk if d[:7] == str(nxt)]
        prev = [v for d, v in wk if d[:7] == last_m]
        if cur and prev and sum(prev) and int(g["searches"].iloc[-1] or 0):
            est = int(round(int(g["searches"].iloc[-1]) * (sum(cur) / len(cur)) / (sum(prev) / len(prev)), -1))
            months.append({"label": MONTHS[nxt.month - 1] + " (оценка)", "v": est, "est": True})
        out[c] = {"months": months,
                  "avg": None if r is None or pd.isna(r["avg_monthly"]) else int(r["avg_monthly"]),
                  "last": None if r is None or pd.isna(r["last_month"]) else int(r["last_month"]),
                  "last_vs_avg": None if r is None or pd.isna(r["last_vs_avg_pct"]) else int(r["last_vs_avg_pct"]),
                  "cpc": None if r is None or pd.isna(r["cpc"]) else float(r["cpc"])}
    return out


def _tiktok_shop():
    """candidate -> {products, sold_total, sellers, price_median, top:[{link, title, sold, price}]} (TikTok Shop US)."""
    f, fp = Path("data/processed/tiktok_shop.csv"), Path("data/processed/tiktok_shop_products.csv")
    if not f.exists():
        return {}
    s = pd.read_csv(f).set_index("candidate")
    p = pd.read_csv(fp) if fp.exists() and fp.stat().st_size > 5 else pd.DataFrame()
    out = {}
    for c, r in s.iterrows():
        top = []
        if not p.empty:
            g = p[p["candidate"] == c].sort_values("sold", ascending=False).head(3)
            top = [{"link": x.link, "title": str(x.title)[:70], "sold": int(x.sold), "price": x.price} for x in g.itertuples()]
        out[c] = {"products": int(r["products"]), "sold_total": int(r["sold_total"]), "sellers": int(r["sellers"]),
                  "price_median": None if pd.isna(r["price_median"]) else float(r["price_median"]), "top": top}
    return out


def _who_where():
    """candidate -> {age:[{label, v}], female, male, states:[(state, value)]} (DataForSEO Trends, US, 12 months)."""
    fd, fs = Path("data/processed/d4s_demography.csv"), Path("data/processed/d4s_states.csv")
    if not fd.exists():
        return {}
    d = pd.read_csv(fd)
    s = pd.read_csv(fs) if fs.exists() else pd.DataFrame(columns=["candidate", "state", "value"])
    out = {}
    for c, g in d.groupby("candidate"):
        age = g[g["group"] == "age"]
        gen = g[g["group"] == "gender"].set_index("type")["value"]
        top = s[s["candidate"] == c].sort_values("value", ascending=False).head(5)
        out[c] = {"age": [{"label": t, "v": int(v)} for t, v in zip(age["type"], age["value"])],
                  "female": int(gen.get("female", 0)), "male": int(gen.get("male", 0)),
                  "states": [[x.state, int(x.value)] for x in top.itertuples()]}
    return out


def _extras():
    """candidate -> {sat, pin_demo, brands_hist}: Amazon saturation (run_saturation.py), Pinterest age/gender
    (run_pinterest_extra.py) and brand new-arrivals over 2 years from the web archive (run_brand_history.py)."""
    out = {}
    f = Path("data/processed/amazon_saturation.csv")
    if f.exists():
        for r in pd.read_csv(f).itertuples():
            out.setdefault(r.candidate, {})["sat"] = {
                "results": None if pd.isna(r.results) else int(r.results), "brands": int(r.brands_page1),
                "median_reviews": None if pd.isna(r.median_reviews) else int(r.median_reviews),
                "share_1000": None if pd.isna(r.share_1000_reviews) else float(r.share_1000_reviews),
                "price": None if pd.isna(r.median_price) else float(r.median_price)}
    f = Path("data/processed/pinterest_demographics.csv")
    if f.exists():
        d = pd.read_csv(f).drop_duplicates("term").set_index("term")
        alias = pinterest_aliases()
        for c in pd.read_csv("config/candidates.csv")["candidate"]:
            t = c if c in d.index else alias.get(c)   # wording Pinterest knows (flannel shirt women -> flannel shirt)
            if t in d.index:
                x = d.loc[t]
                ages = {k[4:]: x[k] for k in d.columns if k.startswith("age_") and pd.notna(x[k])}
                top = sorted(ages.items(), key=lambda kv: -kv[1])[:2]
                out.setdefault(c, {})["pin_demo"] = {"top": [[a, round(v * 100)] for a, v in top],
                                                     "female": None if pd.isna(x["female"]) else round(x["female"] * 100)}
    f = Path("data/processed/temu.csv")   # run_temu.py: Temu US search, page 1 (user logged in 23.09.2026)
    if f.exists():
        for r in pd.read_csv(f).itertuples():
            out.setdefault(r.candidate, {})["temu"] = {"products": int(r.products), "sold_total": int(r.sold_total),
                                                     "sold_top": int(r.sold_top), "top_link": r.top_link if isinstance(r.top_link, str) else "",
                                                     "price": None if pd.isna(r.price_median) else float(r.price_median)}
    f = Path("data/processed/meta_web.csv")   # run_meta_adlib_web.py: US ads on the public Meta Ad Library site
    if f.exists():
        for r in pd.read_csv(f).itertuples():
            out.setdefault(r.candidate, {})["meta"] = {"ads": int(r.active_ads), "sampled": int(r.sampled),
                                                     "advertisers": int(r.advertisers), "long": int(r.running_30d_plus),
                                                     "top": r.top_advertisers if isinstance(r.top_advertisers, str) else ""}
    f = Path("data/processed/meta_ads.csv")   # run_meta_ads.py: official API, ads delivered in the EU/UK
    if f.exists():
        for r in pd.read_csv(f).itertuples():
            out.setdefault(r.candidate, {})["meta_eu"] = {"ads": int(r.ads), "advertisers": int(r.advertisers),
                                                        "long": int(r.running_30d_plus),
                                                        "aud28": None if pd.isna(r.aud28_median) else int(r.aud28_median)}
    f = Path("data/processed/brand_history.csv")
    if f.exists():
        h = pd.read_csv(f)
        h["month"] = pd.to_datetime(h["month"])
        last = h["month"].max()
        now = h[h["month"] > last - pd.DateOffset(months=3)]
        ago = h[(h["month"] > last - pd.DateOffset(months=15)) & (h["month"] <= last - pd.DateOffset(months=12))]
        for c in [col for col in h.columns if col not in ("brand", "month", "items")]:
            share = lambda g: g[c].sum() / g["items"].sum() * 100 if g["items"].sum() else None
            out.setdefault(c, {})["brands_hist"] = {"now": share(now), "ago": share(ago),
                                                    "now_n": int(now[c].sum()), "ago_n": int(ago[c].sum()),
                                                    "months": int(h["month"].nunique())}
    return out


def _variants(n=8):
    """candidate -> [[phrase, volume]] most searched versions of the item (run_variant_volumes.py), seed excluded."""
    f = Path("data/processed/variant_volumes.csv")
    if not f.exists():
        return {}
    v = pd.read_csv(f).dropna(subset=["volume"])
    out = {}
    for c, g in v.groupby("candidate"):
        g = g[~g["phrase"].isin([c, c.replace(" women", ""), f"{c} women", f"{c} for women"])]
        g = g.sort_values("volume", ascending=False).drop_duplicates("volume").head(n)   # same volume = same phrase variant
        out[c] = [[p, int(x)] for p, x in zip(g["phrase"], g["volume"])]
    return out


MONTHS = "янв фев мар апр май июн июл авг сен окт ноя дек".split()


def _split(pts):
    """The whole 2-year weekly curve, oldest first."""
    pts = pts[-2 * WEEKS:]
    if len(pts) < WEEKS + 4:
        return None
    vals = [v for _, v in pts]
    sparse = sum(1 for v in vals if v) / len(vals) < MIN_NONZERO
    return {"dates": [d for d, _ in pts], "vals": vals, "sparse": sparse}


def gaps_html(gaps) -> str:
    """Static 'what the radar is missing' cards for the local page (styles live in BLOCK)."""
    if not gaps:
        return ""
    e = html.escape
    cards = "".join(
        f'<div class="rd-gap"><div class="rd-gap-head"><b>{e(g["what"])}</b><span>{e(g["have"])}</span></div>'
        f'<div class="rd-gap-why">{e(g["why"])}</div><div class="rd-gap-fix">→ {e(g["fix"])}</div></div>'
        for g in gaps)
    return (f'<h2 class="rd-h2">Чего не хватает радару</h2>'
            f'<p class="rd-lead">Что ещё не собирается или собрано не по всем кандидатам.</p>'
            f'<div class="rd-gaps">{cards}</div>')


def build_block(cand: pd.DataFrame, with_header: bool, date_str: str, archive_note: str = "",
                gaps=None) -> str:
    pin, goo = _pinterest_series(), _google_series()
    yt = _google_series("data/normalized/google_trends_youtube")
    shop = _google_series("data/normalized/google_trends_shopping")
    aliases = pinterest_aliases()
    amz, ttw, ig = _amazon_months(), _tiktok_weeks(), _instagram()
    gvol, ttshop = _google_volume(), _tiktok_shop()
    who = _who_where()
    variants = _variants()
    extras = _extras()
    # colour follows the item (color_slot 1-8 in config/candidates.csv, else its place there), never its rank on the page
    cfg = pd.read_csv("config/candidates.csv")
    order = {c: i for i, c in enumerate(cfg["candidate"])}
    fixed = dict(zip(cfg["candidate"], cfg["color_slot"])) if "color_slot" in cfg else {}
    # up to 3 fresh US TikTok videos under our hashtag (run_tiktok_tags.py), most viewed first
    tt_links = {}
    vf = Path("data/processed/tiktok_tag_videos.csv")
    if vf.exists():
        from datetime import date, timedelta
        v = pd.read_csv(vf)
        v = v[(v["region"].fillna("US") == "US") & (v["created"].astype(str) >= str(date.today() - timedelta(days=30)))]
        for c, g in v.sort_values("views", ascending=False).groupby("candidate", sort=False):
            tt_links[c] = [{"link": x.link, "views": int(x.views or 0), "created": str(x.created)} for x in g.head(3).itertuples()]
    rows = []
    for _, r in cand.iterrows():
        name = r["candidate"]
        rec = json.loads(r.to_json(force_ascii=False))
        s = fixed.get(name)
        rec["color_slot"] = int(s) if pd.notna(s) and s else order.get(name, 0) % 8 + 1
        rec["tt_links"] = tt_links.get(name, [])
        rec["amz_months"] = amz.get(name, [])
        rec["tt_weeks"] = ttw.get(name, [])
        rec["ig"] = ig.get(name)
        rec["gvol"] = gvol.get(name)
        rec["shop"] = ttshop.get(name)
        rec["who"] = who.get(name)
        rec["variants"] = variants.get(name, [])
        rec["extra"] = extras.get(name, {})
        rec["pin_curve"] = _split(pin[name]) if name in pin else None
        rec["pin_alias"] = aliases.get(name, "")
        rec["google_curve"] = _split(goo[name]) if name in goo else None
        rec["shop_curve"] = None   # Google Shopping removed 24.09.2026
        rec["youtube_curve"] = _split(yt[name]) if name in yt else None
        rows.append(rec)
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    n_curves = sum(1 for x in rows if x["pin_curve"] or x["google_curve"] or x["shop_curve"] or x["youtube_curve"])
    header = f"""
  <div class="rd-eyebrow">Новый радар · 6 каналов · данные на {date_str}</div>
  <h1 class="rd-h1">Кривые по каждому кандидату</h1>
  <p class="rd-lead">Вся кривая интереса за 2 года, неделя за неделей. Радар сравнивает последние 8 недель с теми же неделями
  год назад. Если справа горб выше, чем год назад, — вещь растёт по-настоящему;
  если горбы одинаковые — это сезон, который повторяется каждый год. Шкала 0–100: 100 — пик интереса к слову за 2 года.</p>""" if with_header else ""
    archive = gaps_html(gaps) + (f'<div class="rd-archive">{archive_note}</div>\n' if archive_note else "")
    return BLOCK.replace("__HEADER__", header).replace("__ARCHIVE__", archive).replace("__DATA__", data) \
        .replace("__NCURVES__", str(n_curves)).replace("__NTOTAL__", str(len(rows)))


BLOCK = r"""<!-- RADAR:START (генерируется build_dashboard.py — правки вручную затрутся) -->
<style>
  .rd { --rd-surface: var(--surface-1, var(--surface)); --rd-soft: var(--surface-2);
        --rd-text: var(--text-primary, var(--text)); --rd-text-2: var(--text-secondary, var(--text-2));
        --rd-line: var(--series-1, var(--bar)); --rd-grid: var(--gridline, var(--border));
        --rd-prev: var(--baseline, var(--muted));
        --rd-good: #2f7d5b; --rd-good-bg: rgba(47,125,91,.13);
        --rd-warn: #a0671a; --rd-warn-bg: rgba(160,103,26,.14);
        --rd-hot: #b0472f; --rd-hot-bg: rgba(176,71,47,.13);
        /* 8-slot categorical palette (validated for CVD), one colour per item */
        --c1: #2a78d6; --c2: #eb6834; --c3: #1baf7a; --c4: #eda100;
        --c5: #e87ba4; --c6: #008300; --c7: #4a3aa7; --c8: #e34948; }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .rd {
        --rd-good: #6cc49a; --rd-good-bg: rgba(108,196,154,.16); --rd-warn: #e0a857; --rd-warn-bg: rgba(224,168,87,.16);
        --rd-hot: #e5876f; --rd-hot-bg: rgba(229,135,111,.16);
        --c1: #3987e5; --c2: #d95926; --c3: #199e70; --c4: #c98500;
        --c5: #d55181; --c6: #008300; --c7: #9085e9; --c8: #e66767; } }
  :root[data-theme="dark"] .rd {
        --rd-good: #6cc49a; --rd-good-bg: rgba(108,196,154,.16); --rd-warn: #e0a857; --rd-warn-bg: rgba(224,168,87,.16);
        --rd-hot: #e5876f; --rd-hot-bg: rgba(229,135,111,.16);
        --c1: #3987e5; --c2: #d95926; --c3: #199e70; --c4: #c98500;
        --c5: #d55181; --c6: #008300; --c7: #9085e9; --c8: #e66767; }
  .rd { margin-bottom: 44px; }
  .rd-eyebrow { font: 600 11.5px "IBM Plex Mono", "JetBrains Mono", ui-monospace, monospace; letter-spacing: .09em;
                text-transform: uppercase; color: var(--rd-line); }
  .rd-h1 { font-size: clamp(24px, 3.4vw, 34px); line-height: 1.15; margin: 6px 0 8px; text-wrap: balance; }
  .rd-lead { color: var(--rd-text-2); font-size: 14.5px; max-width: 70ch; line-height: 1.55; margin: 0; }
  .rd-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px; margin-top: 16px; }
  .rd-legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 12px; color: var(--rd-text-2); }
  .rd-legend svg { vertical-align: middle; margin-right: 5px; }
  .rd-filters { display: flex; gap: 6px; flex-wrap: wrap; margin-left: auto; }
  .rd-filters button { font: 600 12.5px inherit; font-family: inherit; color: var(--rd-text-2); background: var(--rd-surface);
                       border: 1px solid var(--border); border-radius: 999px; padding: 6px 13px; min-height: 34px; cursor: pointer; }
  .rd-filters button[aria-pressed="true"] { background: var(--rd-text); color: var(--page); border-color: var(--rd-text); }
  .rd-filters button:focus-visible { outline: 2px solid var(--rd-line); outline-offset: 2px; }
  /* one wide card per row, charts two-up inside: the curves are the point of the page */
  .rd-grid { display: grid; grid-template-columns: 1fr; gap: 18px; margin-top: 16px; }
  .rd-charts { display: grid; grid-template-columns: 1fr; gap: 18px; }   /* one chart per row, full card width */
  .rd-card { background: var(--rd-surface); border: 1px solid var(--border); border-left: 8px solid var(--k, var(--border));
             border-radius: 12px; padding: 18px 22px; display: flex; flex-direction: column; gap: 12px; }
  .rd-sw { display: inline-block; width: 14px; height: 14px; border-radius: 4px; background: var(--k); margin-right: 8px;
           vertical-align: -1px; }
  .rd-card.is-test { border-color: var(--rd-good); border-left-color: var(--k, var(--rd-good)); box-shadow: 0 0 0 1px var(--rd-good); }
  .rd-head { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; }
  .rd-name { font-weight: 600; font-size: 18px; line-height: 1.3; }
  .rd-sub { font-size: 12.5px; color: var(--muted); margin-top: 2px; }
  .rd-pills { display: flex; gap: 5px; flex-wrap: wrap; justify-content: flex-end; }
  .rd-pill { font: 600 11px "IBM Plex Mono", "JetBrains Mono", monospace; padding: 3px 8px; border-radius: 999px; white-space: nowrap; }
  .rd-pill.TEST { background: var(--rd-good-bg); color: var(--rd-good); }
  .rd-pill.WATCH { background: var(--rd-warn-bg); color: var(--rd-warn); }
  .rd-pill.LATER { background: var(--rd-soft); color: var(--rd-text-2); border: 1px dashed var(--border); }
  .rd-pill.REJECT { background: var(--rd-soft); color: var(--muted); }
  .rd-pill.season { background: var(--rd-hot-bg); color: var(--rd-hot); }
  .rd-checks { display: flex; gap: 4px; align-items: center; }
  .rd-chk { width: 24px; height: 24px; border-radius: 6px; display: grid; place-items: center;
            font: 600 10.5px "IBM Plex Mono", "JetBrains Mono", monospace; }
  .rd-chk.on { background: var(--rd-good-bg); color: var(--rd-good); }
  .rd-chk.off { background: var(--rd-soft); color: var(--muted); opacity: .75; }
  .rd-nums { margin-left: auto; font: 500 12px "IBM Plex Mono", "JetBrains Mono", monospace; color: var(--rd-text-2);
             font-variant-numeric: tabular-nums; text-align: right; }
  .rd-nums .up { color: var(--rd-good); } .rd-nums .down { color: var(--rd-hot); }
  .rd-chart-label { font: 600 13px "IBM Plex Mono", "JetBrains Mono", monospace; text-transform: uppercase;
                    letter-spacing: .05em; color: var(--rd-text-2); margin-bottom: 4px; }
  .rd-card svg { display: block; width: 100%; height: auto; overflow: visible; cursor: crosshair; touch-action: pan-y; }
  .rd-g { stroke: var(--rd-grid); stroke-width: 1; }
  .rd-t { fill: var(--muted); font-family: "IBM Plex Mono", "JetBrains Mono", monospace; font-size: 17px; }
  .rd-bar { fill: var(--k, var(--rd-line)); }
  .rd-bar.rd-est { fill-opacity: .38; stroke: var(--k, var(--rd-line)); stroke-width: 2; stroke-dasharray: 6 4; }
  .rd-bv { fill: var(--rd-text-2); font-weight: 600; }
  .rd-now { fill: none; stroke: var(--k, var(--rd-line)); stroke-width: 3.5; stroke-linejoin: round; stroke-linecap: round; }
  .rd-q { font-family: "IBM Plex Mono", "JetBrains Mono", monospace; color: var(--rd-text-2); }
  .rd-why { font-size: 12px; color: var(--rd-hot); background: var(--rd-hot-bg); border-radius: 6px; padding: 5px 8px; }
  .rd-sparse { color: var(--rd-hot); text-transform: none; letter-spacing: 0; }
  .rd-manual { font-size: 12px; color: var(--rd-warn); background: var(--rd-warn-bg); border-radius: 6px; padding: 5px 8px; }
  .rd-band-now { fill: var(--rd-good-bg); }
  .rd-band-prev { fill: var(--rd-prev); fill-opacity: .28; }
  .rd-year { stroke: var(--rd-prev); stroke-dasharray: 2 2; }
  .rd-hl { stroke: var(--rd-prev); stroke-width: 1; opacity: 0; pointer-events: none; }
  .rd-hd { fill: var(--k, var(--rd-line)); stroke: var(--rd-surface); stroke-width: 2; opacity: 0; pointer-events: none; }
  .rd-nocurve { font-size: 12px; color: var(--muted); background: var(--rd-soft); border-radius: 8px; padding: 14px 12px; }
  .rd-foot { font-size: 13px; color: var(--rd-text-2); line-height: 1.55; border-top: 1px solid var(--border); padding-top: 10px; }
  .rd-foot b { color: var(--muted); font-weight: 600; font-family: "IBM Plex Mono", "JetBrains Mono", monospace; font-size: 11px; letter-spacing: .04em; }
  .rd-foot a { color: var(--rd-text); text-decoration-color: var(--k, var(--rd-line)); text-underline-offset: 3px; }
  .rd-tip { position: fixed; pointer-events: none; z-index: 30; background: var(--rd-text); color: var(--page);
            font: 11.5px/1.4 "IBM Plex Mono", "JetBrains Mono", monospace; padding: 5px 9px; border-radius: 6px;
            opacity: 0; transform: translate(-50%, -130%); white-space: nowrap; }
  .rd-h2 { font-size: 22px; margin: 40px 0 6px; text-wrap: balance; }
  .rd-gaps { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; margin-top: 14px; }
  .rd-gap { background: var(--rd-surface); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px;
            display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
  .rd-gap-head { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
  .rd-gap-head span { font: 600 11.5px "IBM Plex Mono", "JetBrains Mono", monospace; color: var(--rd-warn); white-space: nowrap; }
  .rd-gap-why { color: var(--rd-text-2); }
  .rd-gap-fix { color: var(--muted); }
  .rd-archive { margin-top: 40px; padding-top: 18px; border-top: 1px dashed var(--border); font-size: 13px; color: var(--muted); }
  @media (max-width: 520px) { .rd-filters { margin-left: 0; } }
</style>
<section class="rd" aria-label="Новый тренд-радар">
__HEADER__
  <div class="rd-bar">
    <div class="rd-legend">
      <span><svg width="22" height="8" aria-hidden="true"><line x1="0" y1="4" x2="22" y2="4" class="rd-now"/></svg>интерес за 2 года</span>
      <span>кривые есть у __NCURVES__ из __NTOTAL__</span>
    </div>
    <div class="rd-filters" role="group" aria-label="Фильтр по решению">
      <button type="button" data-f="ALL" aria-pressed="true">Все</button>
      <button type="button" data-f="TEST" aria-pressed="false">Тестировать</button>
      <button type="button" data-f="WATCH" aria-pressed="false">Наблюдать</button>
      <button type="button" data-f="LATER" aria-pressed="false">Позже</button>
      <button type="button" data-f="REJECT" aria-pressed="false">Отказ</button>
    </div>
  </div>
  <div class="rd-grid" id="rd-grid"></div>
  <div class="rd-tip" id="rd-tip"></div>
</section>
<script id="rd-data" type="application/json">__DATA__</script>
<script>
(() => {
  const ROWS = JSON.parse(document.getElementById("rd-data").textContent);
  const grid = document.getElementById("rd-grid"), tip = document.getElementById("rd-tip");
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const MON = ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"];
  const DEC = { TEST: "тестировать", WATCH: "наблюдать", LATER: "позже", REJECT: "отказ" };
  const CH = [["check_google","G","Google"],["check_pinterest","P","Pinterest"],["check_youtube","Y","YouTube"],["check_tiktok","T","TikTok"],
              ["check_amazon","A","Amazon"],["check_retailers","R","Бренды"],["check_instagram","I","Instagram"]];
  const W = 1100, H = 340, L = 52, R = 12, T = 14, B = 36, pw = W - L - R, ph = H - T - B;
  const x = (i, n) => L + (i / (n - 1)) * pw, y = (v) => T + (1 - v / 100) * ph;
  const fmtDate = (s) => { const [yy, mm, dd] = s.split("-"); return `${+dd} ${MON[+mm - 1]} ${yy}`; };
  const signed = (v) => v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${Math.round(v)}%`;
  const cls = (v) => v > 0 ? "up" : v < 0 ? "down" : "";

  function path(vals) {
    let d = "", on = false;
    vals.forEach((v, i) => {
      if (v === null || v === undefined) { on = false; return; }
      d += (on ? "L" : "M") + x(i, vals.length).toFixed(1) + "," + y(v).toFixed(1) + " "; on = true;
    });
    return d.trim();
  }
  function band(i0, i1, n, cls) {
    const a = x(Math.max(0, i0), n), b = x(Math.min(n - 1, i1), n);
    return `<rect class="${cls}" x="${a.toFixed(1)}" y="${T}" width="${(b - a).toFixed(1)}" height="${ph}"/>`;
  }
  function chart(c, label) {
    if (!c) return "";
    const n = c.dates.length;
    let last = null;
    // a tick per quarter (янв/апр/июл/окт), with the year on January
    const ticks = c.dates.map((d, i) => {
      const m = +d.slice(5, 7);
      if (m === last) return ""; last = m;
      if (i < 2 || i > n - 3 || (m - 1) % 3 !== 0) return "";
      const tx = x(i, n).toFixed(1);
      const lab = m === 1 ? `янв’${d.slice(2, 4)}` : MON[m - 1];
      return `<line class="rd-g${m === 1 ? " rd-year" : ""}" x1="${tx}" x2="${tx}" y1="${T}" y2="${T + ph}"/><text class="rd-t" x="${tx}" y="${H - 9}" text-anchor="middle">${lab}</text>`;
    }).join("");
    // the two windows the radar compares: last 8 weeks and the same 8 weeks a year earlier
    const bands = "";   // user 23.09.2026: no green/grey comparison bands on the charts
    const note = c.sparse ? ' <span class="rd-sparse">· мало поисков — не учитываем</span>' : "";
    return `<div><div class="rd-chart-label">${label}${note}</div>
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${label}: вся кривая за 2 года">
        ${bands}
        <line class="rd-g" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}"/>
        <line class="rd-g" x1="${L}" x2="${W - R}" y1="${y(50)}" y2="${y(50)}"/>
        <line class="rd-g" x1="${L}" x2="${W - R}" y1="${y(100)}" y2="${y(100)}"/>
        <text class="rd-t" x="${L - 10}" y="${y(100) + 6}" text-anchor="end">100</text><text class="rd-t" x="${L - 10}" y="${y(50) + 6}" text-anchor="end">50</text><text class="rd-t" x="${L - 10}" y="${y(0) + 6}" text-anchor="end">0</text>
        ${ticks}
        <path class="rd-now" d="${path(c.vals)}"/>
        <line class="rd-hl" x1="0" x2="0" y1="${T}" y2="${T + ph}"/><circle class="rd-hd" r="8"/>
      </svg></div>`;
  }
  // Bar chart for short counted series (Amazon months, TikTok weeks): value printed above each bar
  const bigN = (n) => n >= 1e6 ? (n / 1e6).toFixed(1).replace(".0", "") + " млн" : n >= 1e3 ? Math.round(n / 1e3) + " тыс." : String(n);
  function bars(pts, label) {
    if (!pts || !pts.length || !pts.some((p) => p.v > 0)) return "";
    const BH = 230, bt = 30, bb = 34, bph = BH - bt - bb, n = pts.length, max = Math.max(...pts.map((p) => p.v));
    const slot = pw / n, bw = Math.min(90, slot * 0.62);
    const marks = pts.map((p, i) => {
      const cx = L + slot * (i + 0.5), h = max ? (p.v / max) * bph : 0, yb = bt + bph - h;
      const rect = h > 0 ? `<path class="rd-bar${p.est ? " rd-est" : ""}" d="M${(cx - bw / 2).toFixed(1)},${(bt + bph).toFixed(1)} V${(yb + 4).toFixed(1)} q0,-4 4,-4 H${(cx + bw / 2 - 4).toFixed(1)} q4,0 4,4 V${(bt + bph).toFixed(1)} Z"><title>${esc(p.label)}: ${p.v}</title></path>` : "";
      return rect + `<text class="rd-t rd-bv" x="${cx.toFixed(1)}" y="${(yb - 8).toFixed(1)}" text-anchor="middle">${bigN(p.v)}</text>`
        + `<text class="rd-t" x="${cx.toFixed(1)}" y="${BH - 10}" text-anchor="middle">${esc(p.label)}</text>`;
    }).join("");
    return `<div><div class="rd-chart-label">${label}</div>
      <svg viewBox="0 0 ${W} ${BH}" role="img" aria-label="${label}">
        <line class="rd-g" x1="${L}" x2="${W - R}" y1="${bt + bph}" y2="${bt + bph}"/>${marks}
      </svg></div>`;
  }
  function wire(svg, c) {
    const n = c.dates.length, hl = svg.querySelector(".rd-hl"), hd = svg.querySelector(".rd-hd");
    const hide = () => { hl.style.opacity = 0; hd.style.opacity = 0; tip.style.opacity = 0; };
    svg.addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect();
      const i = Math.max(0, Math.min(n - 1, Math.round((((e.clientX - r.left) / r.width * W) - L) / pw * (n - 1))));
      const v = c.vals[i]; if (v === null || v === undefined) return hide();
      const px = x(i, n);
      hl.setAttribute("x1", px); hl.setAttribute("x2", px); hl.style.opacity = 1;
      hd.setAttribute("cx", px); hd.setAttribute("cy", y(v)); hd.style.opacity = 1;
      const p = i >= 52 ? c.vals[i - 52] : null;
      tip.textContent = `${fmtDate(c.dates[i])} · ${Math.round(v)}` + (p === null || p === undefined ? "" : ` · год назад ${Math.round(p)}`);
      tip.style.left = e.clientX + "px"; tip.style.top = e.clientY + "px"; tip.style.opacity = 1;
    });
    svg.addEventListener("pointerleave", hide);
  }

  function render(f) {
    grid.innerHTML = "";
    ROWS.filter((r) => f === "ALL" || r.decision === f).forEach((r) => {
      const card = document.createElement("article");
      card.className = "rd-card" + (r.decision === "TEST" ? " is-test" : "");
      card.style.setProperty("--k", `var(--c${r.color_slot || 1})`);
      const chips = CH.map(([k, s, nm]) => `<span class="rd-chk ${r[k] ? "on" : "off"}" title="${nm}: ${r[k] ? "подтверждает" : "не видит"}">${s}</span>`).join("");
      const pinNums = r.pin_yoy_pct === null && r.pin_mom_pct === null ? "нет на Pinterest"
        : `месяц <span class="${cls(r.pin_mom_pct)}">${signed(r.pin_mom_pct)}</span> · к году <span class="${cls(r.pin_yoy_pct)}" title="среднее за 8 недель против тех же недель прошлого года">${signed(r.pin_yoy_pct)}</span>`;
      const curves = bars(r.gvol && r.gvol.months, "Google · сколько раз искали за месяц (США, реальные числа; текущий месяц — оценка по неделям Google Trends)")
        + chart(r.pin_curve, "Pinterest · интерес 0–100" + (r.pin_alias ? ` · по фразе «${esc(r.pin_alias)}»` : ""))
        + chart(r.google_curve, "Google · интерес 0–100")
        + chart(r.youtube_curve, "YouTube · поиск 0–100")
        + ((r.amz_months || []).some((m) => m.label.includes("устарело"))
          ? bars(r.amz_months, "Amazon · сколько раз искали за месяц (США) — у сервиса только старые месяцы, свежее лето и осень он по этой фразе не отдаёт; в решениях радара не используется")
          : bars(r.amz_months, "Amazon · сколько раз искали за месяц (США"
          + (r.amazon_search_phrase && r.amazon_search_phrase !== r.candidate ? `; по близкой фразе «${esc(r.amazon_search_phrase)}»` : "")
          + "; последний полный месяц — сервис отдаёт месяц после его окончания)"))
        + bars(r.who && r.who.age, "Кто ищет в Google США · возраст (0–100, 100 — самая активная группа)")
        + bars(r.tt_weeks, `TikTok США · новых видео в неделю под #${esc(r.tt_hashtag || "")} (по выборке до 90 видео)`);
      const foot = [];
      if (r.gvol && r.gvol.avg !== null) {
        const g = r.gvol;
        foot.push(`<b>GOOGLE США</b> в среднем ${bigN(g.avg)} поисков в месяц, в последний месяц ${bigN(g.last)}`
          + (g.last_vs_avg !== null ? ` (${g.last_vs_avg > 0 ? "+" : ""}${g.last_vs_avg}% к среднему за год)` : "")
          + (g.cpc ? `; клик в рекламе ~$${g.cpc.toFixed(2)}` : ""));
      }
      if (r.variants && r.variants.length) {
        foot.push(`<b>КАКИЕ ВАРИАНТЫ ИЩУТ (Google США, в месяц)</b> ` + r.variants.map((v) => `${esc(v[0])} — ${bigN(v[1])}`).join(" · "));
      }
      if (r.who) {
        const w = r.who, tot = w.female + w.male;
        foot.push(`<b>КТО И ГДЕ ИЩЕТ</b> женщины ${tot ? Math.round(w.female / tot * 100) : "—"}%, мужчины ${tot ? Math.round(w.male / tot * 100) : "—"}%`
          + (w.states.length ? `; больше всего интереса в штатах: ${w.states.map((s) => esc(s[0]) + " " + s[1]).join(", ")}` : ""));
      }
      if (r.shop && r.shop.products) {
        const s = r.shop;
        const links = (s.top || []).map((p) => `<a href="${esc(p.link)}" target="_blank" rel="noopener">${bigN(p.sold)} продано${p.price ? `, $${Number(p.price).toFixed(0)}` : ""}</a>`).join(" · ");
        foot.push(`<b>TIKTOK SHOP США</b> у ${s.products} похожих товаров продано ${bigN(s.sold_total)} шт., продавцов ${s.sellers}`
          + (s.price_median ? `, цена обычно $${s.price_median.toFixed(0)}` : "") + (links ? `<br>самые продаваемые: ${links}` : ""));
      }
      // Amazon lines are always shown: an empty source says why instead of silently disappearing
      foot.push(r.amazon_items ? `<b>AMAZON</b> в хитах и новинках ${r.amazon_items} шт, медиана $${Number(r.amazon_median_price).toFixed(2)}`
        : `<b>AMAZON</b> в хитах и новинках женской одежды этой вещи нет`);
      const stale = (r.amz_months || []).find((m) => m.label.includes("устарело"));
      if (!r.amazon_monthly_searches) foot.push(stale
        ? `<b>ПОИСК AMAZON</b> свежих данных нет — последние у сервиса за ${esc(stale.label.replace(" (устарело)", ""))}`
        : `<b>ПОИСК AMAZON</b> нет данных — Trends MCP не знает эту фразу и похожие`);
      else if (r.amazon_search_phrase && r.amazon_search_phrase !== r.candidate)
        foot.push(`<b>ПОИСК AMAZON</b> по близкой фразе «${esc(r.amazon_search_phrase)}»: ${Math.round(r.amazon_monthly_searches / 1000)} тыс./мес, `
          + `${r.amazon_mcp_lift_pct > 0 ? "+" : ""}${Math.round(r.amazon_mcp_lift_pct)}% к прошлому месяцу`);
      else foot.push(`<b>ПОИСК AMAZON</b> ${Math.round(r.amazon_monthly_searches / 1000)} тыс./мес, `
        + `${r.amazon_mcp_lift_pct > 0 ? "+" : ""}${Math.round(r.amazon_mcp_lift_pct)}% к прошлому месяцу`);
      if (r.amazon_bought_sum) foot.push(`<b>КУПИЛИ НА AMAZON</b> за месяц ≥ ${Number(r.amazon_bought_sum).toLocaleString("ru-RU")} шт. `
        + `(у ${r.amazon_bought_items} товаров с первой страницы поиска есть пометка «bought in past month»)`);
      if (r.ig && r.ig.sampled) {
        const ig = r.ig, pd = ig.per_day;
        const rate = pd === null ? "" : pd >= 1 ? `≈ ${pd} постов в день` : `≈ ${Math.round(pd * 7 * 10) / 10} постов в неделю`;
        const links = (ig.top || []).map((p) => `<a href="${esc(p.link)}" target="_blank" rel="noopener">${bigN(p.likes)} лайков, ${esc(p.date.slice(5))}</a>`).join(" · ");
        foot.push(ig.sample === "top"
          ? `<b>INSTAGRAM #${esc(ig.tag)}</b> ${ig.sampled} лучших постов с ${esc(ig.oldest)} (свежие посты сервис сейчас не отдаёт — частоту не посчитать, проверка Instagram не засчитана)`
            + (links ? `<br>самые залайканные: ${links}` : "")
          : `<b>INSTAGRAM #${esc(ig.tag)}</b> ${rate} (последние ${ig.sampled} постов с ${esc(ig.oldest)}, весь мир)`
            + (ig.likes_median !== null ? `, обычно ${bigN(ig.likes_median)} лайков` : "") + (links ? `<br>самые залайканные свежие: ${links}` : ""));
      }
      foot.push(r.retailer_brands ? `<b>БРЕНДЫ</b> ${esc(r.retailer_list)}`
        : `<b>БРЕНДЫ</b> сейчас ни один из 8 брендов (Zara, ASOS, H&M, Mango, Aritzia, Free People, Urban Outfitters, Abercrombie) эту вещь в новинках не выпускает`);
      // a missing chart is a real answer, not a forgotten source — say why
      const none = [];
      if (!r.pin_curve) none.push("Pinterest — фразы нет в Pinterest Trends: он ведёт статистику только по запросам выше своего порога популярности (искали все формулировки)");
      if (!r.youtube_curve) none.push("YouTube — фразу почти не ищут на YouTube (за 2 года 1–2 ненулевые недели)");
      if (none.length) foot.push(`<b>НЕТ ГРАФИКА</b> ${none.map(esc).join("; ")}`);
      const ex = r.extra || {};
      if (ex.brands_hist && (ex.brands_hist.now_n || ex.brands_hist.ago_n)) {
        const bh = ex.brands_hist, f1 = (v) => v === null || v === undefined ? "—" : v.toFixed(1) + "%";
        foot.push(`<b>БРЕНДЫ ЗА 2 ГОДА (веб-архив)</b> доля в новинках за последние 3 месяца ${f1(bh.now)} (${bh.now_n} шт.), `
          + `год назад ${f1(bh.ago)} (${bh.ago_n} шт.)`);
      }
      if (r.aud28_pct !== null && r.aud28_pct !== undefined)
        foot.push(`<b>АУДИТОРИЯ 28+</b> ${r.aud28_pct}% интереса (${esc(r.aud28_source)})`
          + (r.aud28_pct >= 50 ? " — наша аудитория" : " — слишком молодая"));
      if (ex.pin_demo) foot.push(`<b>КТО ИЩЕТ В PINTEREST</b> ${ex.pin_demo.top.map(([a, v]) => `${esc(a)} лет — ${v}%`).join(", ")}`
        + (ex.pin_demo.female !== null ? `; женщины ${ex.pin_demo.female}%` : ""));
      if (ex.meta) {
        const m = ex.meta;
        foot.push(`<b>РЕКЛАМА КОНКУРЕНТОВ (Meta, США)</b> активных объявлений ~${bigN(m.ads)}; в выборке ${m.sampled}: `
          + `${m.advertisers} рекламодателей, ${m.long} идут 30+ дней (долгая реклама обычно окупается)`
          + (m.top ? `<br>чаще всех: ${esc(m.top)}` : "")
          + (m.ads > 10000 ? "<br>⚠ число завышено: фраза совпадает с чужой рекламой (не про одежду)" : ""));
      }
      if (ex.meta_eu) {
        const m = ex.meta_eu;
        foot.push(`<b>РЕКЛАМА В ЕВРОПЕ (Meta API)</b> ${m.ads} объявлений, ${m.advertisers} рекламодателей, ${m.long} идут 30+ дней`
          + (m.aud28 !== null ? `; охват от 28 лет ~${m.aud28}%` : ""));
      }
      if (ex.temu) {
        const t = ex.temu;
        foot.push(`<b>TEMU США</b> на 1-й странице поиска ${t.products} похожих товаров, продано ${bigN(t.sold_total)} шт., `
          + `лидер — ${bigN(t.sold_top)} шт.` + (t.top_link ? ` (<a href="${esc(t.top_link)}" target="_blank" rel="noopener">товар</a>)` : "")
          + (t.price ? `, цена обычно $${t.price.toFixed(2)}` : ""));
      }
      if (ex.sat) {
        const s = ex.sat;
        foot.push(`<b>НАСЫЩЕНИЕ AMAZON</b> ${s.results ? `больше ${bigN(s.results)} товаров` : "товаров —"}, `
          + `на 1-й странице ${s.brands} брендов, медиана отзывов ${s.median_reviews ?? "—"}, `
          + `с 1000+ отзывов ${s.share_1000 !== null ? Math.round(s.share_1000 * 100) + "%" : "—"}`
          + (s.share_1000 !== null ? (s.share_1000 >= 0.4 ? " — ниша занята старыми продавцами" : s.share_1000 <= 0.1 ? " — ниша свободная" : "") : ""));
      }
      if (r.google_rising_top) foot.push(`<b>GOOGLE</b> ${esc(String(r.google_rising_top).split(" | ")[0])}`);
      if (r.tiktok_hashtags) foot.push(`<b>TIKTOK</b> ${esc(r.tiktok_hashtags)}`);
      if (r.tt_hashtag && r.tt_total_videos !== null && r.tt_total_videos !== undefined) {
        const big = (n) => n >= 1e6 ? (n / 1e6).toFixed(1) + " млн" : n >= 1e3 ? Math.round(n / 1e3) + " тыс." : String(n);
        const links = (r.tt_links || []).map((v) => `<a href="${esc(v.link)}" target="_blank" rel="noopener">${big(v.views)} просм., ${esc(v.created.slice(5))}</a>`).join(" · ");
        foot.push(`<b>TIKTOK США #${esc(r.tt_hashtag)}</b> всего ${big(r.tt_total_videos)} видео, ${big(r.tt_total_views)} просмотров; `
          + `свежих американских за 30 дней: ${r.tt_us_fresh} из ${r.tt_us_sampled}` + (links ? `<br>свежие видео: ${links}` : ""));
      }
      if (r.ac_modifiers) {
        const words = String(r.ac_modifiers).split(" | ").slice(0, 8).map((m) => m.split(" (")[0]);
        foot.push(`<b>ДОПИСЫВАЮТ В ПОИСКЕ</b> ${esc(words.join(", "))}`
          + (r.ac_colors ? `; цвета: ${esc(r.ac_colors)}` : ""));
      }
      if (r.yt_views_90d !== null && r.yt_views_90d !== undefined) {
        const vy = r.yt_views_yoy_pct;
        foot.push(`<b>YOUTUBE</b> видео за 90 дн: ${(r.yt_views_90d / 1e6).toFixed(1)} млн просмотров`
          + (vy === null || vy === undefined ? "" : ` (${vy > 0 ? "+" : ""}${Math.round(vy)}% к тем же дням год назад)`)
          + `; «где купить / хочу» — ${r.yt_intent_comments} из ${r.yt_comments_read} комментариев`
          + (r.yt_intent_examples ? `<br><span style="color:var(--muted)">«${esc(String(r.yt_intent_examples).split(" | ").slice(0, 2).join("», «"))}»</span>` : ""));
      }
      card.innerHTML = `
        <div class="rd-head">
          <div><div class="rd-name"><span class="rd-sw" aria-hidden="true"></span>${esc(r.candidate)}</div><div class="rd-sub">${r.checks_passed} из ${CH.length} каналов подтверждают${r.season_months ? ` · сезон: ${esc(r.season_months)}${r.season_source === "вручную" ? " (задан вручную)" : ""}` : ""}</div></div>
          <div class="rd-pills"><span class="rd-pill ${r.decision}">${DEC[r.decision]}</span>${r.short_season ? '<span class="rd-pill season">короткий сезон</span>' : r.seasonal_flag ? '<span class="rd-pill season">сезон</span>' : ""}</div>
        </div>
        <div class="rd-checks">${chips}<span class="rd-nums">${pinNums}</span></div>
        ${r.pin_quarters ? `<div class="rd-sub">Pinterest по кварталам к прошлому году: <span class="rd-q">${esc(r.pin_quarters)}</span></div>` : ""}
        ${r.reject_reason ? `<div class="rd-why">Почему отказ: ${esc(r.reject_reason)}</div>` : ""}
        ${r.later_reason ? `<div class="rd-manual">Позже: ${esc(r.later_reason)}</div>` : ""}
        ${r.watch_reason && r.decision === "WATCH" ? `<div class="rd-sub">Почему наблюдать: ${esc(r.watch_reason)}</div>` : ""}
        ${r.manual_reason ? `<div class="rd-manual">Ручное решение: ${esc(r.manual_reason)} · автоматически было бы «${DEC[r.auto_decision] || r.auto_decision}»</div>` : ""}
        ${curves ? `<div class="rd-charts">${curves}</div>` : '<div class="rd-nocurve">Кривой нет: ни Pinterest, ни Google, ни YouTube не дали 2-летней истории по этому запросу.</div>'}
        ${foot.length ? `<div class="rd-foot">${foot.join("<br>")}</div>` : ""}`;
      grid.appendChild(card);
      const svgs = card.querySelectorAll("svg[role=img]");
      [r.pin_curve, r.google_curve, r.shop_curve, r.youtube_curve].filter(Boolean).forEach((c, i) => wire(svgs[i], c));
    });
    if (!grid.children.length) grid.innerHTML = '<p class="rd-lead">Нет кандидатов в этой группе.</p>';
  }
  render("ALL");
  document.querySelectorAll(".rd-filters button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".rd-filters button").forEach((o) => o.setAttribute("aria-pressed", String(o === b)));
    render(b.dataset.f);
  }));
})();
</script>
__ARCHIVE__<!-- RADAR:END -->
"""
