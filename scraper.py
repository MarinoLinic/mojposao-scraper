import os
import json
import random
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

SEARCHES = [
    {
        "name": "part_time",
        "url": "https://mojposao.hr/pretraga-poslova?locations=Zagreb&employmentType=4",
        "seen_file": "seen_jobs_part_time.json",
    },
    {
        "name": "it",
        "url": "https://mojposao.hr/pretraga-poslova?locations=Grad+Zagreb+i+Zagreba%C4%8Dka+%C5%BEupanija&locations=Zagreb&positions=IT,+telekomunikacije&sortBy=adtype",
        "seen_file": "seen_jobs_it.json",
    },
]

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.2 Safari/605.1.15",
]


def load_seen_jobs(filepath):
    if not os.path.exists(filepath):
        return {}
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_seen_jobs(filepath, seen_jobs):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(seen_jobs, f, ensure_ascii=False, indent=2)


def fetch_page_content(url):
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"  Error fetching {url}: {e}")
        return None


def parse_job_data(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    jobs = []
    container = soup.find("div", class_="search-results")
    if not container:
        print("  Could not find the search results container.")
        return jobs

    for element in container.find_all(recursive=False):
        if (
            element.find("span", class_="illustration_header__message")
            and "Nemamo više poslova" in element.text
        ):
            print("  Found recommendation section. Stopping.")
            break

        for card in element.find_all("div", class_="job-card"):
            title_el = card.find("h3", {"data-test": "job-card-content-title"})
            link_el = card.find("a", href=True)
            date_el = card.find("time")

            if title_el and link_el:
                jobs.append({
                    "title": title_el.get_text(strip=True),
                    "link": "https://mojposao.hr" + link_el["href"],
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

    count_line = f"*{escape_md(label)}* \u2014 {len(jobs_list)} new job{'s' if len(jobs_list) != 1 else ''}\\!\n"
    lines = [count_line]
    for job in jobs_list:
        lines.append(
            f"*{escape_md(job['title'])}*\n"
            f"Prijava do: {escape_md(job['date'])}\n"
            f"[Link za prijavu]({job['link']})\n"
            f"\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\- "
        )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": "\n".join(lines),
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
        print(f"  [{label}] Notification sent.")
    except requests.RequestException as e:
        print(f"  [{label}] Failed to send notification: {e}")
        if hasattr(e, "response") and e.response:
            print(f"  Telegram response: {e.response.text}")


def run_search(search):
    name = search["name"]
    label = "Part-time (Zagreb)" if name == "part_time" else "IT / Telekomunikacije (Zagreb)"
    print(f"\n[{name}] Starting...")

    seen_jobs = load_seen_jobs(search["seen_file"])
    print(f"  Loaded {len(seen_jobs)} previously seen jobs.")

    html = fetch_page_content(search["url"])
    if not html:
        print(f"  Could not fetch page. Skipping.")
        return

    current_jobs = parse_job_data(html)
    print(f"  Found {len(current_jobs)} jobs on page.")

    new_jobs = [job for job in current_jobs if job["link"] not in seen_jobs]
    print(f"  {len(new_jobs)} new jobs.")

    for job in current_jobs:
        seen_jobs[job["link"]] = {"title": job["title"], "date": job["date"]}

    save_seen_jobs(search["seen_file"], seen_jobs)
    print(f"  Saved {len(seen_jobs)} total seen jobs to {search['seen_file']}.")

    send_telegram_message(new_jobs, label)


def main():
    print("Starting job scraper...")
    for search in SEARCHES:
        run_search(search)
    print("\nScraper finished.")


if __name__ == "__main__":
    main()