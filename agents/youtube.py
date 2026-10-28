from playwright.sync_api import sync_playwright


def open_youtube():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://youtube.com")


def search_and_play(query):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        page.goto("https://youtube.com")

        page.fill('input[name="search_query"]', query)
        page.keyboard.press("Enter")

        page.wait_for_timeout(2000)

        page.click("ytd-video-renderer")