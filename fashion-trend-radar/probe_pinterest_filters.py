"""Recon: which query params trends.pinterest.com sends for the Interest / Age / Gender / Include keyword filters.
Opens a new tab in the open Dolphin profile 3, clicks the filters, logs top_trends_filtered calls and filter options."""
import json
import time
import urllib.parse
from pathlib import Path

from playwright.sync_api import sync_playwright

from run_retailers import cdp_endpoint

OUT = Path("data/raw/pinterest_trends")


def main():
    calls, options = [], []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_endpoint())
        page = browser.contexts[0].new_page()

        def on_resp(resp):
            u = urllib.parse.unquote(resp.url)
            if "top_trends_filtered" in u:
                calls.append(u)
            elif "available_interests" in u or "moment/available" in u:
                try:
                    options.append({"url": u[:160], "body": resp.json()})
                except Exception:
                    pass
        page.on("response", on_resp)
        page.goto("https://trends.pinterest.com/?country=US", timeout=60000)
        time.sleep(10)
        for label in ("Gender", "Age", "Interest"):
            page.get_by_role("button", name=label).first.click()
            time.sleep(2)
            (OUT / f"probe_filter_{label}.txt").write_text(page.inner_text("body")[:6000], encoding="utf-8")
            first = page.locator("[role=dialog] input[type=checkbox], [role=listbox] [role=option], [role=menu] [role=menuitemcheckbox]")
            print(label, "вариантов на экране:", first.count())
            if first.count():
                first.nth(0).click(force=True)
                time.sleep(4)
            page.keyboard.press("Escape")
            time.sleep(1)
        page.close()
    print("\n".join(calls))
    (OUT / "probe_filter_options.json").write_text(json.dumps(options, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
