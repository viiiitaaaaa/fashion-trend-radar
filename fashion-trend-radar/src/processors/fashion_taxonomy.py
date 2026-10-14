"""
Decomposes a fashion keyword into Category + Silhouette + Material + Detail
+ Audience/Occasion instead of treating it as one indivisible token. Lets
you aggregate trend momentum by attribute ("fitted + lace + going_out is
rising") rather than only by exact keyword string. Independent of the
scoring modules -- feed its output columns into anything downstream.
"""

from __future__ import annotations

import re
import pandas as pd


TAXONOMY = {
    "category": {
        "top": ["top", "blouse", "shirt", "tee", "t-shirt", "tank"],
        "dress": ["dress", "maxi", "midi", "mini dress"],
        "trousers": [
            "trousers", "pants", "jeans", "cargo",
            "wide leg", "barrel leg", "leggings",
        ],
        "skirt": ["skirt", "mini skirt", "maxi skirt"],
        "set": ["set", "matching set", "two piece", "co-ord"],
        "knitwear": ["cardigan", "sweater", "knit", "pullover"],
        "outerwear": ["jacket", "coat", "blazer", "shacket"],
    },
    "silhouette": {
        "fitted": ["fitted", "bodycon", "slim fit", "tight"],
        "oversized": ["oversized", "baggy", "relaxed"],
        "wide_leg": ["wide leg", "wide-leg"],
        "barrel_leg": ["barrel leg", "barrel-leg"],
        "flare": ["flare", "flared"],
        "maxi": ["maxi", "longline", "floor length"],
        "cropped": ["cropped", "crop top"],
        "high_waist": ["high waist", "high-waisted"],
    },
    "material": {
        "linen": ["linen"],
        "cotton": ["cotton"],
        "ribbed": ["ribbed"],
        "knit": ["knit", "knitted"],
        "mesh": ["mesh", "sheer"],
        "lace": ["lace", "lace trim"],
        "satin": ["satin"],
        "denim": ["denim"],
        "cashmere": ["cashmere"],
        "wool": ["wool"],
        "faux_fur": ["faux fur", "fur"],
        "leather": ["leather", "faux leather"],
        "suede": ["suede"],
        "sequin": ["sequin", "embellished"],
        "flannel": ["flannel"],
    },
    "pattern": {
        "plaid": ["plaid", "tartan", "gingham"],
        "leopard": ["leopard", "animal print"],
        "stripe": ["stripe", "striped"],
        "floral": ["floral", "flower"],
        "polka_dot": ["polka dot", "polka-dot"],
    },
    "neckline": {
        "roll_neck": ["roll neck", "rollneck", "turtleneck", "funnel neck", "mock neck"],
        "boat_neck": ["boat neck", "boatneck"],
        "v_neck": ["v-neck", "v neck"],
        "halter": ["halter"],
        "off_shoulder": ["off shoulder", "off-shoulder"],
    },
    "detail": {
        "lace_trim": ["lace trim", "lace-trim"],
        "ruffle": ["ruffle", "ruffled"],
        "bow": ["bow", "bows", "bowed", "bow detail"],
        "fringe": ["fringe"],
        "drawstring": ["drawstring"],
        "pockets": ["pocket", "pockets"],
        "adjustable": ["adjustable", "adjustable straps"],
        "lined": ["lined", "fully lined"],
    },
    "audience_occasion": {
        "petite": ["petite", "short girl", "short women"],
        "plus_size": ["plus size", "curve", "curvy"],
        "modest": ["modest", "covered"],
        "travel": ["travel", "airport outfit", "vacation"],
        "workwear": ["workwear", "office", "business casual"],
        "going_out": ["going out", "night out", "party"],
        "maternity": ["maternity", "pregnancy", "bump friendly"],
    },
}


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


_COMPILED: dict = {}


def _pattern_re(pattern: str):
    # Whole-word match: "lace" must not hit "necklace", "bow" not "rainbow".
    p = pattern.strip()
    if p not in _COMPILED:
        _COMPILED[p] = re.compile(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])")
    return _COMPILED[p]


def extract_fashion_features(text: str) -> dict:
    text = normalize_text(text)

    result = {}

    for group_name, labels in TAXONOMY.items():
        matches = []

        for label, patterns in labels.items():
            if any(_pattern_re(pattern).search(text) for pattern in patterns):
                matches.append(label)

        result[group_name] = matches

    return result


def decompose_keywords(
    df: pd.DataFrame,
    keyword_col: str = "keyword"
) -> pd.DataFrame:
    data = df.copy()

    extracted = data[keyword_col].apply(
        extract_fashion_features
    )

    for group_name in TAXONOMY:
        data[group_name] = extracted.apply(
            lambda row: "|".join(row[group_name])
        )

    return data


def aggregate_by_feature(
    df: pd.DataFrame,
    feature_col: str,
    metric_col: str = "fashion_score"
) -> pd.DataFrame:
    exploded = (
        df.assign(
            feature=df[feature_col]
            .fillna("")
            .str.split("|")
        )
        .explode("feature")
    )

    exploded = exploded[exploded["feature"] != ""]

    return (
        exploded
        .groupby("feature", as_index=False)
        .agg(
            candidate_count=("keyword", "nunique"),
            avg_score=(metric_col, "mean"),
            max_score=(metric_col, "max"),
        )
        .sort_values("avg_score", ascending=False)
    )
