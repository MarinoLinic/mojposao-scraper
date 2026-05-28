# MojPosao Job Scraper

This is an automated web scraping tool designed to find and report new job listings from the Croatian job board, [mojposao.hr](https://mojposao.hr).

## What it Does

The project automates the process of checking for specific job opportunities. Its main functions are:

1.  **Daily Scraping**: A GitHub Actions workflow runs the scraper every day on a schedule.
2.  **Multiple searches**: It tracks both Zagreb part-time listings and IT / Telekomunikacije listings for Zagreb.
3.  **Notification**: If any new jobs are found, it sends a Telegram notification with titles, deadlines, and links.
4.  **Seen-job tracking**: The workflow can commit and push updated `seen_jobs` JSON files back to the repository.

This eliminates the need to manually check the website every day.

## How It Works

- **Scraper (`scraper.py`)**: A Python script using `requests` and `BeautifulSoup` to fetch and parse the job listings pages for two configured searches.
- **Automation (`.github/workflows/daily-job-scrape.yml`)**: A GitHub Actions workflow that runs daily at `06:00 UTC` and can also be triggered manually via `workflow_dispatch`.
- **Push updates**: The workflow may add and push updated `seen_jobs_part_time.json` and `seen_jobs_it.json` files when new job state is recorded.
- **Notifications**: The scraper sends Telegram messages via the Bot API using repository secrets.
- **Exploratory tooling (`capture_network.py`)**: A separate optional helper for capturing browser network traffic and discovering hidden APIs during investigation.

## Setup

To get this project running in your own GitHub repository, follow these steps:

1.  **Dependencies**: The project requires Python and the libraries listed in `requirements.txt`.

2.  **Create a Telegram Bot**:

    - Chat with `@BotFather` on Telegram to create a new bot.
    - Save the **Bot Token** he gives you.

3.  **Get Your Chat ID**:

    - Start a chat with your new bot and send it a message.
    - Visit `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` in your browser (replacing `<YOUR_BOT_TOKEN>` with your token) to find your `chat_id`.

4.  **Configure GitHub Secrets**:
    - In your GitHub repository, go to `Settings` > `Secrets and variables` > `Actions`.
    - Create the following two repository secrets:
      - `TELEGRAM_BOT_TOKEN`: The token you saved earlier.
      - `TELEGRAM_CHAT_ID`: The chat ID you found.

### Local Testing

To test the script locally without triggering the GitHub workflow:

1.  Install the required libraries: `pip install -r requirements.txt`.
2.  Create a file named `.env` in the root directory.
3.  Add your secrets to the `.env` file:
    ```
    TELEGRAM_BOT_TOKEN="your_bot_token_goes_here"
    TELEGRAM_CHAT_ID="your_chat_id_goes_here"
    ```
4.  Ensure the `.env` file is listed in your `.gitignore` to prevent committing your secrets.
5.  Run the script: `python scraper.py`.

### Optional API discovery helper

If you want to investigate hidden endpoints or capture network traffic from the browser, use `capture_network.py`:

1.  Install Playwright: `pip install playwright`
2.  Install a browser runtime: `playwright install chromium`
3.  Update the URL list in `capture_network.py` and run: `python capture_network.py`
4.  Review the generated artifacts such as `network_log.json`, `api_candidates.json`, and `api_report.txt`.
