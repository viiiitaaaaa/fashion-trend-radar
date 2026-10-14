"""Rebuild tiktok_tags / instagram_tags / tiktok_shop rows from saved treg answers (data/raw/treg), no paid calls.
Used 23.09.2026 after a partial run overwrote the tables. Usage: .venv/Scripts/python.exe restore_treg.py "cand" ..."""
import json
import sys
from collections import defaultdict
from pathlib import Path

import run_instagram_tags as ig
import run_tiktok_tags as tt

RAW = Path("data/raw/treg")
files = sorted(RAW.glob("*.json"))


def tt_call(endpoint, **params):
    tag = "_".join(str(v) for v in params.values())[:60]
    hits = [f for f in files if f.name.endswith(f"_{endpoint}_{tag}.json")]
    if not hits:
        raise RuntimeError(f"нет сохранённого ответа {endpoint} {tag}")
    return json.loads(hits[-1].read_text(encoding="utf-8"))


ig_queue = defaultdict(list)


def ig_call(**params):
    kw = params["keyword"]
    if "pagination_token" not in params:   # first page of a new run: the newest group of pages for this tag
        hits = [f for f in files if f.name.endswith(f"_instagram_{kw}.json")]
        ig_queue[kw] = hits[-ig.PAGES:]
    if not ig_queue[kw]:
        return {"data": {}}
    return json.loads(ig_queue[kw].pop(0).read_text(encoding="utf-8"))


if __name__ == "__main__":
    cands = sys.argv[1:]
    tt.call, ig.call = tt_call, ig_call
    sys.argv = [sys.argv[0]] + cands
    tt.main()
    ig.main()
