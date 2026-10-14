"""Recon: women's new-arrivals pages of 4 retailers (US), Dolphin profile 3.
One view per site; records JSON XHRs that look like product lists, plus
screenshot/page text, so the collector can read what the page itself shows."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\User\dolphin_anty")
from dolphin import DolphinLocal, start_with_retry  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PROFILE = 859648353
SITES = {
    "zara": "https://www.zara.com/us/en/woman-new-in-l1180.html",
    "asos": "https://www.asos.com/us/women/new-in/new-in-clothing/cat/?cid=2623",
    "aritzia": "https://www.aritzia.com/us/en/new",
    "freepeople": "https://www.freepeople.com/new-clothes/",
}
OUT = Path("data/raw/retailers")
OUT.mkdir(parents=True, exist_ok=True)


def looks_like_products(obj, depth=0):
    """True if the JSON contains a list of >=5 dicts with a name/title-ish key."""
    if depth > 6:
        return False
    if isinstance(obj, list) and len(obj) >= 5 and all(isinstance(x, dict) for x in obj[:5]):
        keys = set().union(*(x.keys() for x in obj[:5]))
        if keys & {"name", "title", "productName", "displayName"}:
            return True
    if isinstance(obj, dict):
        return any(looks_like_products(v, depth + 1) for v in obj.values())
    if isinstance(obj, list):
        return any(looks_like_products(v, depth + 1) for v in obj[:3])
    return False


def main():
    only = sys.argv[1:]
    sites = {k: v for k, v in SITES.items() if not only or k in only}
    api = DolphinLocal(port=DolphinLocal.discover() or 3001)
    auto = start_with_retry(api, PROFILE, no_tabs=True)["automation"]
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"ws://127.0.0.1:{auto['port']}{auto['wsEndpoint']}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        for name, url in sites.items():
            hits = []

            def on_resp(resp, hits=hits):
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                if "json" not in (resp.headers.get("content-type") or ""):
                    return
                try:
                    j = resp.json()
                except Exception:
                    return
                if looks_like_products(j):
                    hits.append({"url": resp.url, "json": j})

            page.on("response", on_resp)
            try:
                page.goto(url, timeout=90000, wait_until="domcontentloaded")
                time.sleep(8)
                for _ in range(6):
                    page.mouse.wheel(0, 1300)
                    time.sleep(1.5)
                time.sleep(3)
                page.screenshot(path=str(OUT / f"probe_{name}.png"))
                (OUT / f"probe_{name}.html").write_text(page.content(), encoding="utf-8")
                final, title = page.url, page.title()[:70]
            except Exception as e:
                final, title = f"ERROR {e}"[:120], ""
            page.remove_listener("response", on_resp)
            (OUT / f"probe_{name}_json.json").write_text(json.dumps(hits, ensure_ascii=False), encoding="utf-8")
            print(f"{name:11} product-JSON hits={len(hits)} | {final} | {title}")
            for h in hits[:3]:
                print("     ", h["url"][:140])
            time.sleep(5)
        page.close()


if __name__ == "__main__":
    main()
