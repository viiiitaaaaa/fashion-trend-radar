"""
Freshness/momentum-based trend filter.

Works only off what our Bright Data Google Trends collector actually returns:
a single 12-month weekly series (~53 points, 0-100 index). No 5-year history,
no year-over-year, no related/rising queries are available from that crawler
today -- those checks are NOT implemented here because faking them would be
worse than not having them. If real YoY / breakout-query data becomes
available (either by fetching a second 5-year series, or by adding a second
Bright Data crawler for the "related queries" widget), extend this module
rather than approximate it.
"""

import math
import statistics


def _avg(values):
    return sum(values) / len(values) if values else 0.0


def _growth(current, previous):
    if previous <= 0:
        return 100.0 if current > 0 else 0.0
    return ((current - previous) / previous) * 100.0


def _clean_series(values):
    """Drop missing points -- handles both None and pandas NaN (a float that
    is not equal to itself)."""
    return [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]


def compute_momentum(values):
    """values: chronological list of weekly interest values (None/NaN allowed)."""
    clean = _clean_series(values)
    if len(clean) < 16:
        return None

    last_4w = _avg(clean[-4:])
    prev_4w = _avg(clean[-8:-4])
    last_12w = _avg(clean[-12:])
    prev_12w = _avg(clean[-24:-12]) if len(clean) >= 24 else _avg(clean[:-12])

    mom_growth = _growth(last_4w, prev_4w)
    quarter_growth = _growth(last_12w, prev_12w)

    rest = clean[:-12] if len(clean) > 12 else clean
    baseline_now = statistics.median(clean[-12:])
    baseline_rest = statistics.median(rest) if rest else baseline_now
    baseline_growth = _growth(baseline_now, baseline_rest)

    peak = max(clean)
    below_peak_values = [v for v in clean if v < peak]
    non_peak_baseline = statistics.median(below_peak_values) if below_peak_values else peak
    seasonal_spike_ratio = peak / non_peak_baseline if non_peak_baseline else 1

    current = clean[-1]
    off_peak_pct = _growth(current, peak)  # negative = well below its own peak

    return {
        "mom_growth": round(mom_growth, 1),
        "quarter_growth": round(quarter_growth, 1),
        "baseline_growth": round(baseline_growth, 1),
        "seasonal_spike_ratio": round(seasonal_spike_ratio, 2),
        "off_peak_pct": round(off_peak_pct, 1),
        "current": current,
        "peak": peak,
    }


def classify_trend(m):
    """Classify using only mom/quarter/baseline growth + spike ratio - no
    YoY or related-queries data (see module docstring).

    Categories:
      declining            - losing interest both short and mid term, skip
      reviving_from_spike  - well below a past peak, but climbing again the
                              last 4 weeks -> the interesting "just starting
                              this season" case
      structural_growth    - growing on every horizon we can measure
      early_rising         - strong recent pop, not proven yet mid-term
      weak_signal          - none of the above; low-confidence/flat
    """
    if m is None:
        return "insufficient_data"

    if m["mom_growth"] <= 0 and m["quarter_growth"] <= 0:
        return "declining"

    if m["mom_growth"] > 0 and m["off_peak_pct"] <= -35:
        return "reviving_from_spike"

    if m["mom_growth"] > 0 and m["quarter_growth"] > 0 and m["baseline_growth"] > 0:
        return "structural_growth"

    if m["mom_growth"] > 15 and m["quarter_growth"] > 0:
        return "early_rising"

    return "weak_signal"
