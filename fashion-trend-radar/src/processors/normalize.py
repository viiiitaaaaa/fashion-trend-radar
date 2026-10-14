import re
import pandas as pd

_INVISIBLE_CHARS = re.compile(r"[‎‏‪-‮]")


def _clean_date(raw_date):
    if raw_date is None:
        return None
    return _INVISIBLE_CHARS.sub("", raw_date).strip()


def normalize_brightdata_timeseries(keyword, response):
    rows = []

    timeline = response.get("interest_over_time", [])

    for item in timeline:
        rows.append({
            "keyword": keyword,
            "date": _clean_date(item.get("date")),
            "value": item.get("interest_value"),
        })

    return pd.DataFrame(rows)


def normalize_brightdata_geo_map(keyword, response):
    """The crawler's `regional_interest` field is actually three back-to-back
    top-5 lists from the page (geo ranking, related topics, related queries),
    distinguished only by whether interest_score is populated and whether the
    label carries a " - Topic"/" - Company" suffix. This keeps only the geo
    ranking rows (score present, no topic/company suffix)."""
    rows = []

    for item in response.get("regional_interest", []):
        if item.get("interest_score") is None:
            continue
        rows.append({
            "keyword": keyword,
            "rank": item.get("rank"),
            "location": item.get("region_name"),
            "value": item.get("interest_score"),
        })

    return pd.DataFrame(rows)


_TOPIC_SUFFIX = re.compile(r"\s-\s(Topic|Company|Search term)$", re.I)


def normalize_related_topics_and_queries(keyword, response):
    """Splits the same `regional_interest` blob into related TOPICS and
    related QUERIES (both "Top", not "Rising" -- the page's default tab;
    switching to Rising needs an interaction-code change, see trend-radar
    skill notes)."""
    items = response.get("regional_interest", [])
    scoreless = [it for it in items if it.get("interest_score") is None]

    topics, queries = [], []
    for it in scoreless:
        name = (it.get("region_name") or "").strip()
        if not name:
            continue
        if _TOPIC_SUFFIX.search(name):
            topics.append({"keyword": keyword, "rank": it.get("rank"),
                            "topic": _TOPIC_SUFFIX.sub("", name)})
        else:
            queries.append({"keyword": keyword, "rank": it.get("rank"), "query": name})

    return pd.DataFrame(topics), pd.DataFrame(queries)
