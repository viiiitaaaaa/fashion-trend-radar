"""
Recon for TikTok Creative Center (channel #1 of multi-source discovery).
Opens the popular-hashtags page in Dolphin profile 3 and records every
JSON response the page itself loads from creative_radar_api -- so the
real collector can read the same data the page shows, at human volume.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\User\dolphin_anty")
from dolphin import DolphinLocal, start_with_retry  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PROFILE = 859648353
URL = ("https://ads.tiktok.com/business/creativecenter/inspiration/popular/"
       "hashtag/pc/en?period=7&region=US&industry=22000000000")
OUT = Path("data/raw/tiktok_cc")
OUT.mkdir(parents=True, exist_ok=True)


def main():
    api = DolphinLocal(port=DolphinLocal.discover() or 3001)
    auto = start_with_retry(api, PROFILE, no_tabs=True)["automation"]
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"ws://127.0.0.1:{auto['port']}{auto['wsEndpoint']}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()

        def on_response(resp):
            if resp.request.resource_type not in ("xhr", "fetch"):
                return
            if "json" not in (resp.headers.get("content-type") or ""):
                return
            try:
                body = resp.json()
            except Exception:
                return
            captured.append({"url": resp.url, "status": resp.status, "req": resp.request.post_data, "json": body})

        page.on("response", on_response)
        page.goto(URL, timeout=90000, wait_until="domcontentloaded")
        time.sleep(10)
        try:
            page.get_by_text("All", exact=True).first.click(timeout=10000)
            time.sleep(2)
            opts = page.get_by_text("Apparel", exact=False)
            print("apparel options:", opts.count())
            opts.first.click(timeout=10000)
            time.sleep(6)
        except Exception as e:
            print("dropdown click failed:", e)
            page.screenshot(path=str(OUT / "dropdown_fail.png"))
        for _ in range(6):
            page.mouse.wheel(0, 900)
            time.sleep(1.5)
        time.sleep(4)
        page.screenshot(path=str(OUT / "probe.png"), full_page=False)
        (OUT / "probe_text.txt").write_text(page.inner_text("body"), encoding="utf-8")
        print("final url:", page.url)
        print("title:", page.title())
        page.close()

    (OUT / "probe_responses.json").write_text(
        json.dumps(captured, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"captured {len(captured)} creative_radar_api responses")
    for c in captured:
        print(" ", c["status"], c["url"][:160])


if __name__ == "__main__":
    main()
