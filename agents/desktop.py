import subprocess
import pyautogui


def open_app(app_name):
    app_map = {
        "chrome": "Google Chrome",
        "whatsapp": "WhatsApp",
        "spotify": "Spotify",
        "finder": "Finder"
    }

    if app_name in app_map:
        subprocess.run(["open", "-a", app_map[app_name]])


def scroll_up():
    pyautogui.scroll(500)


def scroll_down():
    pyautogui.scroll(-500)


def press_enter():
    pyautogui.press("enter")


def type_text(text):
    pyautogui.write(text, interval=0.02)