import os
import json
import random
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

URL = "https://mojposao.hr/pretraga-poslova?locations=Zagreb&employmentType=4"
SEEN_JOBS_FILE = "seen_jobs.json"

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


def load_seen_jobs():
    """Loads the set of already-seen job links from the JSON file."""
    if not os.path.exists(SEEN_JOBS_FILE):
        return {}
    with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_seen_jobs(seen_jobs: dict):
    """Saves the seen jobs dict back to the JSON file."""
    with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_jobs, f, ensure_ascii=False, indent=2)


def fetch_page_content(url):
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None


def parse_job_data(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    jobs = []
    search_results_container = soup.find("div", class_="search-results")
    if not search_results_container:
        print("Could not find the main search results container.")
        return jobs

    for element in search_results_container.find_all(recursive=False):
        if element.find("span", class_="illustration_header__message") and "Nemamo više poslova" in element.text:
            print("Found the recommendation section. Stopping.")
            break

        for card in element.find_all("div", class_="job-card"):
            title_element = card.find("h3", {"data-test": "job-card-content-title"})
            link_element = card.find("a", href=True)
            date_element = card.find("time")

            if title_element and link_element:
                title = title_element.get_text(strip=True)
                link = "https://mojposao.hr" + link_element['href']
                date = date_element.get_text(strip=True) if date_element else "No date available."
                jobs.append({"title": title, "link": link, "date": date})
    return jobs


def escape_markdown_v2(text):
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(['\\' + char if char in escape_chars else char for char in text])


def send_telegram_message(jobs_list, is_first_run=False):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not set.")
        return
    if not jobs_list:
        print("No new jobs to send.")
        return

    header = f"Found *{len(jobs_list)}* new job{'s' if len(jobs_list) != 1 else ''}\\!" if not is_first_run \
        else f"First run\\! Loaded *{len(jobs_list)}* existing jobs\\. Future messages will only show new ones\\."

    message_lines = [header + "\n"]

    if not is_first_run:
        for job in jobs_list:
            title = escape_markdown_v2(job['title'])
            date = escape_markdown_v2(job['date'])
            message_lines.append(
                f"*{title}*\n"
                f"Prijava do: {date}\n"
                f"[Link za prijavu]({job['link']})\n"
                f"\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\- "
            )

    text = "\n".join(message_lines)
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'MarkdownV2',
        'disable_web_page_preview': True
    }

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        print(f"Notification sent to Telegram.")
    except requests.RequestException as e:
        print(f"Failed to send Telegram notification: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response from Telegram: {e.response.text}")


def main():
    print("Starting job scraper...")

    seen_jobs = load_seen_jobs()
    is_first_run = len(seen_jobs) == 0
    print(f"Loaded {len(seen_jobs)} previously seen jobs.")

    html = fetch_page_content(URL)
    if not html:
        print("Could not retrieve page content. Exiting.")
        return

    current_jobs = parse_job_data(html)
    print(f"Found {len(current_jobs)} jobs on the page.")

    # Find jobs whose link we've never seen before
    new_jobs = [job for job in current_jobs if job['link'] not in seen_jobs]
    print(f"{len(new_jobs)} new jobs to notify about.")

    # Add ALL current jobs to seen (and keep old deleted ones too)
    for job in current_jobs:
        seen_jobs[job['link']] = {"title": job['title'], "date": job['date']}

    save_seen_jobs(seen_jobs)
    print(f"Saved {len(seen_jobs)} total seen jobs.")

    send_telegram_message(new_jobs, is_first_run=is_first_run)
    print("Scraper finished.")


if __name__ == "__main__":
    main()