import webbrowser


def open_url(url):
    webbrowser.open(url)


def google_search(query):
    url = f"https://www.google.com/search?q={query}"
    webbrowser.open(url)


def open_gmail():
    webbrowser.open("https://mail.google.com")


def open_youtube():
    webbrowser.open("https://youtube.com")