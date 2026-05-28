"""
capture_full_html.py
--------------------
Opens a real browser, loads the search page, waits for jobs to render,
then saves the COMPLETE HTML to a file.

Usage:
  pip install playwright
  playwright install chromium
  python capture_full_html.py

Output: full_page.html (you can open in browser or inspect with BeautifulSoup)
"""

import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SEARCH_URL = (
    "https://mojposao.hr/pretraga-poslova"
    "?locations=Grad+Zagreb+i+Zagreba%C4%8Dka+%C5%BEupanija"
    "&locations=Zagreb"
    "&positions=IT,+telekomunikacije"
    "&sortBy=adtype"
)

OUTPUT_FILE = Path("full_page.html")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=100,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            viewport=None,
            locale="hr-HR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # Warm up
        print("Warming up on homepage...")
        page.goto("https://mojposao.hr", wait_until="domcontentloaded", timeout=15_000)
        time.sleep(2)

        # Load search page
        print(f"\nLoading search page...")
        print(f"URL: {SEARCH_URL}")
        page.goto(SEARCH_URL, wait_until="networkidle", timeout=30_000)
        
        print("Page loaded. Waiting for async content...")
        time.sleep(5)
        
        # Scroll to trigger lazy loading
        print("Scrolling down to trigger lazy loading...")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(3)

        # Get the full HTML
        print("Capturing full HTML...")
        html = page.content()

        # Save it
        OUTPUT_FILE.write_text(html, encoding="utf-8")
        print(f"\nSaved to: {OUTPUT_FILE}")
        print(f"File size: {len(html):,} bytes")

        # Count some indicators
        if "job-card" in html:
            count = html.count("job-card")
            print(f"✓ Found {count} job-card references")
        if "posao" in html.lower():
            count = html.lower().count("posao")
            print(f"✓ Found {count} 'posao' references")

        browser.close()
        print("\nDone!")

if __name__ == "__main__":
    main()