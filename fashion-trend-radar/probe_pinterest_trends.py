"""Recon: trends.pinterest.com (business login) in Dolphin profile 3.
Records every JSON XHR the page loads, plus screenshot and page text."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\User\dolphin_anty")
from dolphin import DolphinLocal, start_with_retry  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PROFILE = 859648353
URL = "https://trends.pinterest.com/?country=US"
OUT = Path("data/raw/pinterest_trends")
OUT.mkdir(parents=True, exist_ok=True)


def main():
    api = DolphinLocal(port=DolphinLocal.discover() or 3001)
    auto = start_with_retry(api, PROFILE, no_tabs=True)["automation"]
    captured = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"ws://127.0.0.1:{auto['port']}{auto['wsEndpoint']}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()

        def on_resp(resp):
            if resp.request.resource_type not in ("xhr", "fetch"):
                return
            if "json" not in (resp.headers.get("content-type") or ""):
                return
            try:
                captured.append({"url": resp.url, "status": resp.status,
                                 "req": resp.request.post_data, "json": resp.json()})
            except Exception:
                pass

        page.on("response", on_resp)
        page.goto(URL, timeout=90000, wait_until="domcontentloaded")
        time.sleep(10)
        for _ in range(5):
            page.mouse.wheel(0, 1000)
            time.sleep(1.5)
        time.sleep(3)
        page.screenshot(path=str(OUT / "probe.png"))
        (OUT / "probe_text.txt").write_text(page.inner_text("body"), encoding="utf-8")
        print("final url:", page.url, "|", page.title()[:80])
        page.close()

    (OUT / "probe_responses.json").write_text(json.dumps(captured, ensure_ascii=False), encoding="utf-8")
    print(f"captured {len(captured)} JSON responses")
    for c in captured:
        print(" ", c["status"], c["url"][:150])


if __name__ == "__main__":
    main()
