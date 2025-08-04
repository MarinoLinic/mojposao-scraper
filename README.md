# MojPosao Job Scraper

This is an automated web scraping tool designed to find and report new job listings from the Croatian job board, [mojposao.hr](https://mojposao.hr).

## What it Does

The project automates the process of checking for specific job opportunities. Its main functions are:

1.  **Daily Scraping**: Every day at 8 AM CEST, the script visits `mojposao.hr`.
2.  **Specific Query**: It filters the jobs for **honorarni poslovi** located in **Zagreb**. It only checks the first page right now.
3.  **Notification**: If any new jobs matching the criteria are found, it sends a notification with the job titles, application deadlines, and direct links to a private Telegram chat.

This eliminates the need to manually check the website every day.

## How It Works

- **Scraper (`scraper.py`)**: A Python script using `requests` to fetch the webpage and `BeautifulSoup` to parse the HTML and extract the relevant job data.
- **Automation (`.github/workflows/daily-job-scrape.yml`)**: A GitHub Actions workflow that runs the Python script on a daily schedule (`cron`).
- **Notifications**: The script uses the Telegram Bot API to send messages. Credentials are kept secure using GitHub Secrets.

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
