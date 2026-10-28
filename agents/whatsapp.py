import subprocess
import pyautogui
import time


def open_whatsapp():
    subprocess.run(["open", "-a", "WhatsApp"])
    time.sleep(2)


def search_contact(name):
    pyautogui.hotkey("command", "f")
    time.sleep(1)
    pyautogui.write(name, interval=0.03)
    time.sleep(2)
    pyautogui.press("enter")
    time.sleep(1)


def write_message(text):
    pyautogui.write(text, interval=0.02)


def send_message():
    pyautogui.press("enter")


def message_contact(name, text):
    open_whatsapp()
    search_contact(name)
    write_message(text)