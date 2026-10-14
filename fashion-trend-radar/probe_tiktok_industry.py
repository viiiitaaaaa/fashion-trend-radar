"""Find which request field filters GetHashtagList by industry (22000000000 =
Apparel & Accessories). Rewrites the page's own request body on the fly,
reloads once per candidate key, checks returned industries."""
import json
import re
import sys
import time

sys.path.insert(0, r"C:\Users\User\dolphin_anty")
from dolphin import DolphinLocal, start_with_retry  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PROFILE = 859648353
URL = ("https://ads.tiktok.com/business/creativecenter/inspiration/popular/"
       "hashtag/pc/en?period=7&region=US")
APPAREL = "22000000000"
CANDIDATES = [
    ("industryIDs", [APPAREL]),
    ("industryIds", [APPAREL]),
    ("industryID", APPAREL),
    ("industryId", APPAREL),
    ("industry", APPAREL),
]


def main():
    api = DolphinLocal(port=DolphinLocal.discover() or 3001)
    auto = start_with_retry(api, PROFILE, no_tabs=True)["automation"]
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"ws://127.0.0.1:{auto['port']}{auto['wsEndpoint']}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()

        for key, val in CANDIDATES:
            got = []

            def handle(route, request, key=key, val=val):
                body = json.loads(request.post_data or "{}")
                body[key] = val
                route.continue_(post_data=json.dumps(body))

            def on_resp(resp):
                if "GetHashtagList" in resp.url:
                    try:
                        got.append(resp.json())
                    except Exception:
                        pass

            page.route(re.compile(r".*GetHashtagList.*"), handle)
            page.on("response", on_resp)
            page.goto(URL, timeout=90000, wait_until="domcontentloaded")
            time.sleep(8)
            for _ in range(4):
                page.mouse.wheel(0, 900)
                time.sleep(1.5)
            time.sleep(4)
            page.unroute(re.compile(r".*GetHashtagList.*"))
            page.remove_listener("response", on_resp)

            if not got:
                print(f"{key}: no response")
                continue
            items = got[0].get("items") or []
            apparel = sum(APPAREL in (it.get("industryIDs") or []) for it in items)
            names = [it["hashtagName"] for it in items[:6]]
            print(f"{key}: status={got[0].get('BaseResp')} items={len(items)} apparel={apparel} top={names}")
            time.sleep(5)
        page.close()


if __name__ == "__main__":
    main()
