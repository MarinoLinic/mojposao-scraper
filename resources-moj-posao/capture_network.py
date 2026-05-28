"""
capture_network.py
------------------
Opens a REAL (visible) browser window, loads the mojposao.hr search pages,
intercepts every XHR/Fetch network call, and dumps results to:

  - network_log.json       → all captured requests/responses
  - api_candidates.json    → filtered calls that look like job-data APIs

Usage:
  pip install playwright
  playwright install chromium
  python capture_network.py

A browser window will open. Watch it load the page, then close by itself.
Check api_candidates.json first — it'll likely have exactly what you need.
"""

import json
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Request, Response

# ── Search URLs to load (same as your existing scraper) ──────────────────────

SEARCH_URLS = [
    {
        "label": "IT / Zagreb",
        "url": (
            "https://mojposao.hr/pretraga-poslova"
            "?locations=Grad+Zagreb+i+Zagreba%C4%8Dka+%C5%BEupanija"
            "&locations=Zagreb"
            "&positions=IT,+telekomunikacije"
            "&sortBy=adtype"
        ),
    },
    {
        "label": "Part-time / Zagreb",
        "url": "https://mojposao.hr/pretraga-poslova?locations=Zagreb&employmentType=4",
    },
]

# How long to wait after page load for XHR calls to complete (seconds)
WAIT_AFTER_LOAD = 5

# Output files
OUTPUT_ALL        = Path("network_log.json")
OUTPUT_CANDIDATES = Path("api_candidates.json")

# ── Filters — what looks like a job-data API call ────────────────────────────

IGNORE_PATTERNS = [
    r"\.js(\?|$)",
    r"\.css(\?|$)",
    r"\.svg(\?|$)",
    r"\.png(\?|$)",
    r"\.ico(\?|$)",
    r"\.woff",
    r"\.ttf",
    r"google",
    r"facebook",
    r"sentry",
    r"gtm",
    r"analytics",
    r"cloudfront",
    r"static\.",
    r"_nuxt/",
]

INTERESTING_PATTERNS = [
    r"/api/",
    r"proxy",
    r"jobs",
    r"search",
    r"posao",
    r"offers",
    r"ads",
]

def is_ignorable(url: str) -> bool:
    return any(re.search(p, url, re.I) for p in IGNORE_PATTERNS)

def is_interesting(url: str) -> bool:
    return any(re.search(p, url, re.I) for p in INTERESTING_PATTERNS)


# ── Main capture logic ────────────────────────────────────────────────────────

def capture_search(page, search: dict, all_entries: list, candidate_entries: list):
    label = search["label"]
    url   = search["url"]
    print(f"\n{'='*60}")
    print(f"Loading: {label}")
    print(f"URL: {url}")
    print(f"{'='*60}")

    response_bodies: dict[str, str] = {}

    def on_response(response: Response):
        req_url = response.url
        if is_ignorable(req_url):
            return
        try:
            ct = response.headers.get("content-type", "")
            if "json" in ct:
                try:
                    body = response.json()
                except Exception:
                    body = response.text()
            else:
                body = None
        except Exception:
            body = None

        entry = {
            "label":        label,
            "url":          req_url,
            "method":       response.request.method,
            "status":       response.status,
            "content_type": response.headers.get("content-type", ""),
            "body":         body,
        }
        all_entries.append(entry)

        if is_interesting(req_url) or (body and isinstance(body, dict)):
            print(f"  [CAPTURE] {response.status} {req_url}")
            if body and isinstance(body, dict):
                print(f"    Keys: {list(body.keys())}")
            candidate_entries.append(entry)

    page.on("response", on_response)

    page.goto(url, wait_until="networkidle", timeout=30_000)
    print(f"  Page loaded. Waiting {WAIT_AFTER_LOAD}s for async calls...")
    time.sleep(WAIT_AFTER_LOAD)

    # Scroll down to trigger any lazy-loaded content
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)

    page.remove_listener("response", on_response)
    print(f"  Done capturing for: {label}")


def main():
    all_entries       = []
    candidate_entries = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,   # VISIBLE browser window
            slow_mo=100,      # slight slowdown so you can watch it
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",  # hide automation flag
            ],
        )
        context = browser.new_context(
            viewport=None,    # use full window size
            locale="hr-HR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # Warm up on homepage first
        print("Warming up on homepage...")
        page.goto("https://mojposao.hr", wait_until="domcontentloaded", timeout=15_000)
        time.sleep(2)

        for search in SEARCH_URLS:
            capture_search(page, search, all_entries, candidate_entries)
            time.sleep(3)

        browser.close()

    # ── Write output files ────────────────────────────────────────────────────

    OUTPUT_ALL.write_text(
        json.dumps(all_entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nAll captured requests → {OUTPUT_ALL}  ({len(all_entries)} entries)")

    OUTPUT_CANDIDATES.write_text(
        json.dumps(candidate_entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"API candidates        → {OUTPUT_CANDIDATES}  ({len(candidate_entries)} entries)")

    # ── Print summary of candidates ───────────────────────────────────────────
    if candidate_entries:
        print("\n--- CANDIDATE SUMMARY ---")
        for e in candidate_entries:
            print(f"  [{e['status']}] {e['method']} {e['url']}")
            if e["body"] and isinstance(e["body"], dict):
                keys = list(e["body"].keys())
                print(f"    → JSON keys: {keys}")
    else:
        print("\nNo candidates found. Check network_log.json for everything.")


if __name__ == "__main__":
    main()