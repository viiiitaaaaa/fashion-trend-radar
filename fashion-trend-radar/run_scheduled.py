"""
Scheduled orchestrator for the trend radar.
  python run_scheduled.py daily    -> Amazon snapshot + rebuild table
  python run_scheduled.py weekly   -> Google rising + 2y history, TikTok 90d,
                                      Pinterest, retailers, then rebuild table
Each step runs as its own process: one failing channel never stops the rest.
Log: data/logs/scheduled_{date}.log
Dolphin-based steps are skipped (logged) if the Dolphin app isn't running.
"""
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
LOG_DIR = ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG = LOG_DIR / f"scheduled_{datetime.now():%Y-%m-%d}.log"


def log(msg):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def dolphin_up():
    try:
        urllib.request.urlopen("http://localhost:3001/v1.0/browser_profiles", timeout=5)
        return True
    except Exception as e:
        # 401/403 still means the app is running
        return "HTTP Error" in str(e)


def run(name, args, needs_dolphin=False, timeout=1800):
    if needs_dolphin and not dolphin_up():
        log(f"SKIP {name}: Dolphin не запущен")
        return False
    log(f"START {name}")
    try:
        p = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
        tail = "\n".join((p.stdout or "").strip().splitlines()[-8:])
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(tail + "\n")
            if p.returncode != 0:
                f.write((p.stderr or "")[-2000:] + "\n")
        log(f"{'OK' if p.returncode == 0 else 'FAIL'} {name} (код {p.returncode})")
        return p.returncode == 0
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT {name}")
        return False


def daily():
    run("amazon", ["run_amazon.py"], needs_dolphin=True)
    run("radar", ["run_radar.py"])


def weekly():
    run("google_rising", ["run_related_queries.py"], timeout=3600)
    candidates = pd.read_csv(ROOT / "config" / "candidates.csv")["candidate"].tolist()
    run("google_history_2y", ["run_trends_bootstrap.py", *candidates], timeout=5400)
    run("tiktok_cc_90d", ["run_tiktok_cc.py"], needs_dolphin=True)
    run("pinterest", ["run_pinterest_trends.py"], needs_dolphin=True)
    run("retailers", ["run_retailers.py"], needs_dolphin=True)
    run("radar", ["run_radar.py"])


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    log(f"===== {mode} run =====")
    {"daily": daily, "weekly": weekly}[mode]()
    log(f"===== {mode} done =====")
