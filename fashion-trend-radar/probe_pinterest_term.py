"""Recon: what trends.pinterest.com loads on a TERM page (related terms, audience...) — open Dolphin profile 3,
new tab only, the user's tabs stay. Output: data/raw/pinterest_trends/probe_term_<term>.json + .png"""
import json
import sys
import time
import urllib.parse
from pathlib import Path

from playwright.sync_api import sync_playwright

from run_retailers import cdp_endpoint

TERM = sys.argv[1] if len(sys.argv) > 1 else "bandana cardigan"
OUT = Path("data/raw/pinterest_trends")


def main():
    captured = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_endpoint())
        ctx = browser.contexts[0]
        page = ctx.new_page()

        def on_resp(resp):
            if resp.request.resource_type in ("xhr", "fetch") and "json" in (resp.headers.get("content-type") or ""):
                try:
                    captured.append({"url": resp.url, "status": resp.status, "body": resp.json()})
                except Exception:
                    pass
        page.on("response", on_resp)
        page.goto("https://trends.pinterest.com/search/?q=" + urllib.parse.quote(TERM) + "&country=US", timeout=60000)
        time.sleep(12)
        for _ in range(4):
            page.mouse.wheel(0, 1500)
            time.sleep(2)
        slug = TERM.replace(" ", "_")
        page.screenshot(path=str(OUT / f"probe_term_{slug}.png"), full_page=True)
        (OUT / f"probe_term_{slug}.txt").write_text(page.inner_text("body"), encoding="utf-8")
        page.close()
    (OUT / f"probe_term_{slug}.json").write_text(json.dumps(captured, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in captured:
        u = urllib.parse.unquote(c["url"])
        print(c["status"], u[:200])


if __name__ == "__main__":
    main()
