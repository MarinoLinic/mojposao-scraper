import os
import json
import random
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SEARCHES = [
    {
        "name": "part_time",
        "url": "https://mojposao.hr/pretraga-poslova"
        "?locations=Zagreb"
        "&employmentType=4",
        "seen_file": "seen_jobs_part_time.json",
        "label": "Part-time (Zagreb)",
    },
    {
        "name": "it",
        "url": (
            "https://mojposao.hr/pretraga-poslova"
            "?locations=Grad+Zagreb+i+Zagreba%C4%8Dka+%C5%BEupanija"
            "&locations=Zagreb"
            "&positions=IT,+telekomunikacije"
            "&sortBy=adtype"
        ),
        "seen_file": "seen_jobs_it.json",
        "label": "IT / Telekomunikacije (Zagreb)",
    },
]

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
]

# How long to wait (seconds) between the homepage warm-up and the actual search page
WARMUP_DELAY = (3, 7)

# How long to wait between the two separate searches
SEARCH_DELAY = (15, 30)

# How long to wait between paginated pages
PAGE_DELAY = (5, 12)

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = (10, 25)

# Request timeout
REQUEST_TIMEOUT = 20

# Optional proxy (set PROXY_URL in .env or environment)
PROXY_URL = os.environ.get("PROXY_URL")


def load_seen_jobs(filepath):
    if not os.path.exists(filepath):
        return {}
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_seen_jobs(filepath, seen_jobs):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(seen_jobs, f, ensure_ascii=False, indent=2)


def make_session():
    """Creates a requests session with a consistent, realistic browser identity."""
    session = requests.Session()
    ua = random.choice(USER_AGENTS)

    is_firefox = "Firefox" in ua
    is_safari = "Safari" in ua and "Chrome" not in ua
    is_chrome = "Chrome" in ua or "Edg" in ua

    if is_firefox:
        accept = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        sec_ch = {}
    elif is_safari:
        accept = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        sec_ch = {}
    else:  # Chrome / Edge
        accept = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
        sec_ch = {
            "Sec-CH-UA": '"Chromium";v="148", "Google Chrome";v="148", "Not-A.Brand";v="99"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"' if "Windows" in ua else '"macOS"',
        }

    session.headers.update({
        "User-Agent": ua,
        "Accept": accept,
        "Accept-Language": "hr-HR,hr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        **sec_ch,
    })

    if PROXY_URL:
        session.proxies = {"http": PROXY_URL, "https": PROXY_URL}

    return session


def warmup_session(session):
    """
    Visits the homepage first to establish cookies and look like a real
    browsing session before hitting the search page.
    """
    try:
        print("  Warming up session on homepage...")
        session.headers.update({
            "Referer": "https://www.google.com/",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-User": "?1",
        })
        session.get("https://mojposao.hr", timeout=REQUEST_TIMEOUT)
        delay = random.uniform(*WARMUP_DELAY)
        print(f"  Waiting {delay:.1f}s before fetching search page...")
        time.sleep(delay)
        # Update referer so the search page looks like it was navigated to from the homepage
        session.headers.update({
            "Referer": "https://mojposao.hr/",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?0",
        })
    except requests.RequestException as e:
        print(f"  Homepage warmup failed (continuing anyway): {e}")


def fetch_page_content(session, url):
    """Fetches a single page with retries on failure."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"  Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                delay = random.uniform(*RETRY_DELAY)
                print(f"  Retrying in {delay:.1f}s...")
                time.sleep(delay)
    print("  All attempts failed.")
    return None


def fetch_all_pages(session, base_url):
    """
    Fetches all paginated result pages for a search URL.
    MojPosao uses ?page=2, ?page=3, etc.
    Returns a list of HTML strings (one per page fetched).
    """
    pages_html = []
    page = 1

    while True:
        separator = "&" if "?" in base_url else "?"
        url = base_url if page == 1 else f"{base_url}{separator}page={page}"
        print(f"  Fetching page {page}: {url}")
        html = fetch_page_content(session, url)
        if not html:
            print(f"  Failed to fetch page {page}. Stopping pagination.")
            break

        pages_html.append(html)

        soup = BeautifulSoup(html, "html.parser")

        # Check if a "next page" link exists; if not, we're done
        next_link = (
            soup.find("a", {"data-test": "pagination-next"}) or
            soup.find("a", attrs={"aria-label": lambda v: v and "next" in v.lower()}) or
            soup.find("a", class_=lambda c: c and "next" in c)
        )

        if page == 1:
            total = parse_total_jobs(html)
            if total:
                print(f"  Page header reports {total} total jobs.")

        if not next_link:
            print(f"  No next-page link found after page {page}. Done.")
            break

        page += 1
        delay = random.uniform(*PAGE_DELAY)
        print(f"  Waiting {delay:.1f}s before next page...")
        time.sleep(delay)

    return pages_html


def parse_total_jobs(html_content):
    """Extracts the total job count shown in the page heading, e.g. '(70)'."""
    soup = BeautifulSoup(html_content, "html.parser")
    heading = soup.find("h1")
    if heading:
        b_el = heading.find("b")
        if b_el:
            try:
                return int(b_el.get_text(strip=True).strip("()"))
            except ValueError:
                pass
    return None


def parse_job_data(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    jobs = []
    seen_links = set()

    container = soup.find("div", class_="search-results")
    if not container:
        print("  Could not find the search results container.")
        return jobs

    for element in container.find_all(recursive=False):
        # Stop at the recommendation section — those aren't real search results
        if element.find("span", class_="illustration_header__message"):
            print("  Found recommendation section. Stopping.")
            break

        for card in element.find_all("div", class_="job-card"):
            title_el = card.find("h3", {"data-test": "job-card-content-title"})
            link_el = card.find("a", href=lambda h: h and h.startswith("/posao/"))
            date_el = card.find("time")

            if not (title_el and link_el):
                continue

            # Strip tracking params so dedup works reliably across runs
            raw_href = link_el["href"]
            clean_href = raw_href.split("?")[0]
            full_link = "https://mojposao.hr" + clean_href

            if full_link in seen_links:
                continue
            seen_links.add(full_link)

            jobs.append({
                "title": title_el.get_text(strip=True),
                "link": full_link,
                "date": date_el.get_text(strip=True) if date_el else "Nema datuma.",
            })
    return jobs


def escape_md(text):
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join('\\' + c if c in escape_chars else c for c in text)


def send_telegram_message(jobs_list, label):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  Telegram credentials not set.")
        return
    if not jobs_list:
        print(f"  [{label}] No new jobs. Skipping notification.")
        return

    def build_job_block(job):
        return (
            f"*{escape_md(job['title'])}*\n"
            f"Prijava do: {escape_md(job['date'])}\n"
            f"[Link za prijavu]({job['link']})\n"
            f"\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\- "
        )

    MAX_CHARS = 3800
    header = f"*{escape_md(label)}* \\- {len(jobs_list)} new job{'s' if len(jobs_list) != 1 else ''}\\!\n\n"

    chunks = []
    current_lines = [header]
    current_len = len(header)

    for job in jobs_list:
        block = build_job_block(job) + "\n"
        if current_len + len(block) > MAX_CHARS:
            chunks.append("".join(current_lines))
            current_lines = []
            current_len = 0
        current_lines.append(block)
        current_len += len(block)

    if current_lines:
        chunks.append("".join(current_lines))

    print(f"  [{label}] Sending {len(jobs_list)} jobs across {len(chunks)} message(s).")

    for i, text in enumerate(chunks):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            print(f"  [{label}] Sent message {i + 1}/{len(chunks)}.")
            if i < len(chunks) - 1:
                time.sleep(1)
        except requests.RequestException as e:
            print(f"  [{label}] Failed to send message {i + 1}: {e}")
            if hasattr(e, "response") and e.response:
                print(f"  Telegram response: {e.response.text}")


def run_search(search):
    print(f"\n[{search['name']}] Starting...")

    seen_jobs = load_seen_jobs(search["seen_file"])
    print(f"  Loaded {len(seen_jobs)} previously seen jobs.")

    session = make_session()
    warmup_session(session)

    pages_html = fetch_all_pages(session, search["url"])
    if not pages_html:
        print(f"  Could not fetch any pages. Skipping.")
        return

    # Parse all pages, deduplicating by link across pages
    all_jobs = []
    seen_links_this_run = set()
    for html in pages_html:
        for job in parse_job_data(html):
            if job["link"] not in seen_links_this_run:
                seen_links_this_run.add(job["link"])
                all_jobs.append(job)

    print(f"  Found {len(all_jobs)} total jobs across {len(pages_html)} page(s).")

    new_jobs = [job for job in all_jobs if job["link"] not in seen_jobs]
    print(f"  {len(new_jobs)} new jobs.")

    for job in all_jobs:
        seen_jobs[job["link"]] = {
            "title": job["title"],
            "date": job["date"],
            "seen_at": datetime.now().isoformat(),
        }

    save_seen_jobs(search["seen_file"], seen_jobs)
    print(f"  Saved {len(seen_jobs)} total seen jobs to {search['seen_file']}.")

    send_telegram_message(new_jobs, search["label"])


def main():
    print("Starting job scraper...")
    for i, search in enumerate(SEARCHES):
        run_search(search)
        if i < len(SEARCHES) - 1:
            delay = random.uniform(*SEARCH_DELAY)
            print(f"\nWaiting {delay:.1f}s before next search...")
            time.sleep(delay)
    print("\nScraper finished.")


if __name__ == "__main__":
    main()