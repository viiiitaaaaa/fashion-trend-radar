import os
import json
import pandas as pd
from datetime import datetime


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def save_json(data, path):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_csv(df, path):
    ensure_dir(os.path.dirname(path))
    if isinstance(df, pd.DataFrame):
        df.to_csv(path, index=False)


def timestamp():
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")
