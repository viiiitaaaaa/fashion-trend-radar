"""Recon: Amazon Movers & Shakers + Best Sellers, Women's Clothing (US), in
Dolphin profile 3. One page view each, screenshot + page text for layout."""
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\User\dolphin_anty")
from dolphin import DolphinLocal, start_with_retry  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PROFILE = 859648353
PAGES = {
    "ms_fashion_root": "https://www.amazon.com/gp/movers-and-shakers/fashion",
    "ms_dresses": "https://www.amazon.com/gp/movers-and-shakers/fashion/1045024",
    "ms_sweaters": "https://www.amazon.com/gp/movers-and-shakers/fashion/1044456",
    "ms_skirts": "https://www.amazon.com/gp/movers-and-shakers/fashion/1045022",
    "ms_jeans": "https://www.amazon.com/gp/movers-and-shakers/fashion/1048188",
    "ms_tops": "https://www.amazon.com/gp/movers-and-shakers/fashion/2368343011",
    "ms_coats": "https://www.amazon.com/gp/movers-and-shakers/fashion/1044646",
    "ms_pants": "https://www.amazon.com/gp/movers-and-shakers/fashion/1048184",
}
OUT = Path("data/raw/amazon")
OUT.mkdir(parents=True, exist_ok=True)


def main():
    api = DolphinLocal(port=DolphinLocal.discover() or 3001)
    auto = start_with_retry(api, PROFILE, no_tabs=True)["automation"]
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"ws://127.0.0.1:{auto['port']}{auto['wsEndpoint']}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        for name, url in PAGES.items():
            page.goto(url, timeout=90000, wait_until="domcontentloaded")
            time.sleep(6)
            for _ in range(5):
                page.mouse.wheel(0, 1200)
                time.sleep(1.2)
            page.screenshot(path=str(OUT / f"probe_{name}.png"))
            (OUT / f"probe_{name}.html").write_text(page.content(), encoding="utf-8")
            (OUT / f"probe_{name}.txt").write_text(page.inner_text("body"), encoding="utf-8")
            print(name, "->", page.url, "|", page.title()[:80])
            time.sleep(4)
        page.close()


if __name__ == "__main__":
    main()
