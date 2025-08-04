import os
import random
import requests
from bs4 import BeautifulSoup

# Local
from dotenv import load_dotenv
load_dotenv()

URL = "https://mojposao.hr/pretraga-poslova?locations=Zagreb&employmentType=4"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# User-Agent Rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.2 Safari/605.1.15",
]


def fetch_page_content(url):
    """Fetches the HTML content"""
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return None


def parse_job_data(html_content):
    """Parses the HTML to extract job listings before the recommendation section."""
    soup = BeautifulSoup(html_content, "html.parser")
    jobs = []
    search_results_container = soup.find("div", class_="search-results")
    if not search_results_container:
        print("Could not find the main search results container.")
        return jobs

    for element in search_results_container.find_all(recursive=False):
        if element.find("span", class_="illustration_header__message") and "Nemamo više poslova" in element.text:
            print("Found the recommendation section. Stopping scrape for relevant jobs.")
            break

        job_cards = element.find_all("div", class_="job-card")
        for card in job_cards:
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
    """Escapes characters for Telegram's MarkdownV2 parse mode."""
    # List of characters to escape as per Telegram's API documentation
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    # Use a comprehension to prepend a backslash to each special character
    return "".join(['\\' + char if char in escape_chars else char for char in text])


def send_telegram_message(jobs_list):
    """Sends message to a Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not set. Please check your .env file or GitHub secrets.")
        return

    if not jobs_list:
        print("No new jobs found. No notification will be sent.")
        return

    # Escape the initial count message as well, just in case
    message_lines = [f"Found *{len(jobs_list)}* new jobs\\!\n"]
    for job in jobs_list:
        # Use the helper function to safely escape any special characters
        title = escape_markdown_v2(job['title'])
        date = escape_markdown_v2(job['date'])

        message_lines.append(
            f"*{title}*\n"
            f"Prijava do: {date}\n"
            f"[Link za prijavu]({job['link']})\n"
            # The separator line must also be escaped
            f"\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\- "
        )

    text = "\n".join(message_lines)
    telegram_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'MarkdownV2',
        'disable_web_page_preview': True
    }

    try:
        response = requests.post(telegram_api_url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"Notification successfully sent to Telegram chat {TELEGRAM_CHAT_ID}.")
    except requests.RequestException as e:
        print(f"Failed to send Telegram notification: {e}")
        if e.response:
            print(f"Response from Telegram: {e.response.text}")


def main():
    print("Starting job scraper...")
    html = fetch_page_content(URL)
    if html:
        jobs = parse_job_data(html)
        print(f"Found {len(jobs)} relevant jobs.")
        if jobs:
            send_telegram_message(jobs)
    else:
        print("Could not retrieve page content. Exiting.")
    print("Scraper finished.")


if __name__ == "__main__":
    main()