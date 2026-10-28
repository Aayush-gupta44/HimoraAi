"""
Himora mac_system.py v2
-----------------------

Advanced macOS control layer for Himora.

This file does NOT contain AI planning.
It contains reliable Mac actions that executor.py can call.

Capabilities:
- Open any app using:
  1. open -a
  2. /Applications search
  3. Spotlight fallback
- Close / activate apps
- Open URLs / Google / YouTube
- Control volume by exact percentage
- Volume up/down by percentage
- Open System Settings and search anything
- Open Wi-Fi/Bluetooth settings
- Turn Wi-Fi on/off
- Turn Bluetooth on/off with blueutil
- Create folders
- Find files/folders using mdfind
- Search in Finder
- Open files/folders
- Keyboard/mouse/click/type/paste/scroll
- Screenshots
- Clipboard
- Notifications

Required macOS permissions:
System Settings -> Privacy & Security:
- Accessibility
- Input Monitoring
- Screen Recording
- Automation

Optional but recommended:
brew install blueutil
brew install brightness
"""

import os
import re
import json
import time
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus


# =========================================================
# OPTIONAL IMPORTS
# =========================================================
try:
    import pyautogui
    pyautogui.FAILSAFE = True
except Exception:
    pyautogui = None

try:
    import pyperclip
except Exception:
    pyperclip = None


# =========================================================
# PATHS
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory_data"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

SCREENSHOT_DIR = MEMORY_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

MAC_STATE_FILE = MEMORY_DIR / "mac_system_state.json"


# =========================================================
# CONFIG
# =========================================================
CONFIG = {
    "default_browser": os.getenv("HIMORA_DEFAULT_BROWSER", "Google Chrome"),
    "command_timeout": 12,
    "after_open_wait": 1.2,
    "after_activate_wait": 0.35,
    "after_click_wait": 0.15,
    "after_type_wait": 0.08,
    "after_hotkey_wait": 0.15,
    "spotlight_wait": 0.55,
    "settings_wait": 1.2,
}


# =========================================================
# RESULT MODEL
# =========================================================
@dataclass
class MacResult:
    ok: bool
    message: str
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =========================================================
# BASIC HELPERS
# =========================================================
def log(message: str):
    print(f"[MAC SYSTEM] {message}")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize(value: Any) -> str:
    return clean_text(value).lower()


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", clean_text(text)).strip()


def sleep(seconds: float):
    time.sleep(seconds)


def save_state(data: Dict[str, Any]):
    try:
        current = {}

        if MAC_STATE_FILE.exists():
            current = json.loads(MAC_STATE_FILE.read_text(encoding="utf-8"))

        current.update(data)
        current["updated_at"] = time.time()

        MAC_STATE_FILE.write_text(
            json.dumps(current, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )

    except Exception as error:
        log(f"Could not save state: {error}")


def require_pyautogui() -> bool:
    if pyautogui is None:
        log("pyautogui is not available.")
        return False

    return True


def tool_exists(name: str) -> str:
    found = shutil.which(name)
    return found or ""


# =========================================================
# SHELL / APPLESCRIPT
# =========================================================
def run_command(
    args: List[str],
    timeout: Optional[int] = None,
    check: bool = False,
) -> Tuple[int, str, str]:
    timeout = timeout or CONFIG["command_timeout"]

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )

        return result.returncode, result.stdout.strip(), result.stderr.strip()

    except subprocess.TimeoutExpired:
        return 124, "", "Command timed out."

    except Exception as error:
        return 1, "", str(error)


def run_shell(
    command: str,
    timeout: Optional[int] = None,
) -> Tuple[int, str, str]:
    timeout = timeout or CONFIG["command_timeout"]

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return result.returncode, result.stdout.strip(), result.stderr.strip()

    except subprocess.TimeoutExpired:
        return 124, "", "Command timed out."

    except Exception as error:
        return 1, "", str(error)


def run_osascript(script: str, timeout: Optional[int] = None) -> str:
    code, out, err = run_command(
        ["osascript", "-e", script],
        timeout=timeout or CONFIG["command_timeout"],
    )

    if code != 0 and err:
        log(f"AppleScript error: {err}")

    return out.strip()


# =========================================================
# APP CONTROL
# =========================================================
APP_ALIASES = {
    "chrome": "Google Chrome",
    "google": "Google Chrome",
    "google chrome": "Google Chrome",
    "safari": "Safari",
    "whatsapp": "WhatsApp",
    "watsapp": "WhatsApp",
    "whats": "WhatsApp",
    "gmail": "Google Chrome",
    "mail": "Mail",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "code": "Visual Studio Code",
    "terminal": "Terminal",
    "finder": "Finder",
    "notes": "Notes",
    "messages": "Messages",
    "facetime": "FaceTime",
    "settings": "System Settings",
    "system settings": "System Settings",
    "spotify": "Spotify",
    "music": "Music",
    "photos": "Photos",
    "calendar": "Calendar",
    "reminders": "Reminders",
    "preview": "Preview",
    "app store": "App Store",
    "calculator": "Calculator",
    "activity monitor": "Activity Monitor",
}


def resolve_app_name(app: str) -> str:
    app = compact_spaces(app)

    if not app:
        return ""

    return APP_ALIASES.get(normalize(app), app)


def application_search_roots() -> List[Path]:
    return [
        Path("/Applications"),
        Path("/System/Applications"),
        Path.home() / "Applications",
    ]


def find_application_path(app: str) -> str:
    app = resolve_app_name(app)

    if not app:
        return ""

    wanted = normalize(app)
    wanted_no_app = wanted.replace(".app", "")

    candidates = []

    for root in application_search_roots():
        if not root.exists():
            continue

        try:
            for path in root.rglob("*.app"):
                name = normalize(path.stem)

                score = 0

                if name == wanted_no_app:
                    score = 100
                elif wanted_no_app in name:
                    score = 80
                elif name in wanted_no_app:
                    score = 70
                else:
                    words = wanted_no_app.split()
                    if all(word in name for word in words):
                        score = 60

                if score:
                    candidates.append((score, str(path)))

        except Exception:
            pass

    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]

    # Spotlight app index fallback.
    code, out, _ = run_command(
        [
            "mdfind",
            f'kMDItemKind == "Application" && kMDItemFSName == "*{app}*"',
        ],
        timeout=6,
    )

    if code == 0 and out:
        for line in out.splitlines():
            if line.endswith(".app"):
                return line.strip()

    return ""


def spotlight_open(query: str) -> str:
    query = compact_spaces(query)

    if not query:
        return "No Spotlight query provided."

    if not require_pyautogui():
        return "Spotlight control is not available."

    pyautogui.hotkey("command", "space")
    sleep(CONFIG["spotlight_wait"])

    if pyperclip:
        pyperclip.copy(query)
        pyautogui.hotkey("command", "v")
    else:
        pyautogui.write(query, interval=0.01)

    sleep(0.65)
    pyautogui.press("enter")
    sleep(CONFIG["after_open_wait"])

    save_state({
        "last_action": "spotlight_open",
        "last_query": query,
    })

    return f"Opened {query} using Spotlight."


def open_app(app: str) -> str:
    app_name = resolve_app_name(app)

    if not app_name:
        return "No app name provided."

    log(f"Opening app: {app_name}")

    code, _, err = run_command(["open", "-a", app_name])

    if code == 0:
        sleep(CONFIG["after_open_wait"])
        save_state({"last_action": "open_app", "last_app": app_name})
        return f"Opening {app_name}."

    app_path = find_application_path(app_name)

    if app_path:
        code, _, err = run_command(["open", app_path])

        if code == 0:
            sleep(CONFIG["after_open_wait"])
            save_state({"last_action": "open_app_path", "last_app": app_name, "path": app_path})
            return f"Opening {Path(app_path).stem}."

    # Final fallback: Spotlight.
    return spotlight_open(app_name)


def activate_app(app: str) -> str:
    app_name = resolve_app_name(app)

    if not app_name:
        return "No app name provided."

    script = f'tell application "{app_name}" to activate'
    run_osascript(script)
    sleep(CONFIG["after_activate_wait"])

    save_state({"last_action": "activate_app", "last_app": app_name})

    return f"Activated {app_name}."


def close_app(app: str) -> str:
    app_name = resolve_app_name(app)

    if not app_name:
        return "No app name provided."

    script = f'''
    tell application "{app_name}"
        quit
    end tell
    '''

    run_osascript(script)
    sleep(0.5)

    save_state({"last_action": "close_app", "last_app": app_name})

    return f"Closed {app_name}."


def force_quit_app(app: str) -> str:
    app_name = resolve_app_name(app)

    if not app_name:
        return "No app name provided."

    code, _, err = run_command(["pkill", "-x", app_name])

    save_state({"last_action": "force_quit_app", "last_app": app_name})

    if code == 0:
        return f"Force closed {app_name}."

    return f"Could not force close {app_name}: {err}"


def is_app_running(app: str) -> bool:
    app_name = resolve_app_name(app)

    script = f'''
    tell application "System Events"
        return exists process "{app_name}"
    end tell
    '''

    out = run_osascript(script)

    return normalize(out) == "true"


def get_frontmost_app() -> str:
    script = '''
    tell application "System Events"
        set frontApp to name of first application process whose frontmost is true
        return frontApp
    end tell
    '''

    return run_osascript(script)


def list_running_apps() -> List[str]:
    script = '''
    tell application "System Events"
        set appNames to name of every application process whose background only is false
        return appNames
    end tell
    '''

    out = run_osascript(script)

    if not out:
        return []

    return [item.strip() for item in out.split(",") if item.strip()]


# =========================================================
# WINDOW CONTROL
# =========================================================
def get_front_window_bounds() -> Optional[Dict[str, int]]:
    script = '''
    tell application "System Events"
        set frontApp to first application process whose frontmost is true
        if (count of windows of frontApp) is 0 then return ""
        set p to position of window 1 of frontApp
        set s to size of window 1 of frontApp
        return ((item 1 of p as string) & "," & (item 2 of p as string) & "," & (item 1 of s as string) & "," & (item 2 of s as string))
    end tell
    '''

    out = run_osascript(script)

    if not out or "," not in out:
        return None

    try:
        x, y, w, h = [int(float(part)) for part in out.split(",")]
        return {"x": x, "y": y, "w": w, "h": h}
    except Exception:
        return None


def get_app_window_bounds(app: str) -> Optional[Dict[str, int]]:
    app_name = resolve_app_name(app)

    script = f'''
    tell application "System Events"
        if exists process "{app_name}" then
            tell process "{app_name}"
                if (count of windows) is 0 then return ""
                set p to position of window 1
                set s to size of window 1
                return ((item 1 of p as string) & "," & (item 2 of p as string) & "," & (item 1 of s as string) & "," & (item 2 of s as string))
            end tell
        end if
    end tell
    '''

    out = run_osascript(script)

    if not out or "," not in out:
        return None

    try:
        x, y, w, h = [int(float(part)) for part in out.split(",")]
        return {"x": x, "y": y, "w": w, "h": h}
    except Exception:
        return None


def maximize_front_window() -> str:
    return hotkey("control", "command", "f")


def minimize_front_window() -> str:
    return hotkey("command", "m")


def close_front_window() -> str:
    return hotkey("command", "w")


# =========================================================
# WEB / URL
# =========================================================
def open_url(url: str, browser: Optional[str] = None) -> str:
    url = clean_text(url)

    if not url:
        return "No URL provided."

    if not re.match(r"^https?://", url):
        url = "https://" + url

    browser = resolve_app_name(browser or CONFIG["default_browser"])

    code, _, err = run_command(["open", "-a", browser, url])

    sleep(CONFIG["after_open_wait"])

    save_state({"last_action": "open_url", "last_url": url, "last_browser": browser})

    if code == 0:
        return f"Opened {url}."

    return f"Could not open URL: {err}"


def google_search(query: str, browser: Optional[str] = None) -> str:
    query = compact_spaces(query)

    if not query:
        return "No search query provided."

    url = "https://www.google.com/search?q=" + quote_plus(query)

    return open_url(url, browser=browser)


def youtube_search(query: str, browser: Optional[str] = None) -> str:
    query = compact_spaces(query)

    if not query:
        return "No YouTube search query provided."

    url = "https://www.youtube.com/results?search_query=" + quote_plus(query)

    return open_url(url, browser=browser)


# =========================================================
# KEYBOARD / MOUSE
# =========================================================
def click(x: int, y: int, clicks: int = 1) -> str:
    if not require_pyautogui():
        return "Mouse control is not available."

    pyautogui.click(int(x), int(y), clicks=int(clicks))
    sleep(CONFIG["after_click_wait"])

    save_state({"last_action": "click", "x": int(x), "y": int(y)})

    return f"Clicked at {x}, {y}."


def double_click(x: int, y: int) -> str:
    return click(x, y, clicks=2)


def right_click(x: int, y: int) -> str:
    if not require_pyautogui():
        return "Mouse control is not available."

    pyautogui.rightClick(int(x), int(y))
    sleep(CONFIG["after_click_wait"])

    return f"Right-clicked at {x}, {y}."


def move_mouse(x: int, y: int, duration: float = 0.2) -> str:
    if not require_pyautogui():
        return "Mouse control is not available."

    pyautogui.moveTo(int(x), int(y), duration=float(duration))

    return f"Moved mouse to {x}, {y}."


def scroll(amount: int = -5) -> str:
    if not require_pyautogui():
        return "Scroll control is not available."

    pyautogui.scroll(int(amount))

    if int(amount) > 0:
        return "Scrolled up."

    return "Scrolled down."


def scroll_down(amount: int = 5) -> str:
    return scroll(-abs(int(amount)))


def scroll_up(amount: int = 5) -> str:
    return scroll(abs(int(amount)))


def press(key: str, presses: int = 1) -> str:
    if not require_pyautogui():
        return "Keyboard control is not available."

    key = clean_text(key)

    if not key:
        return "No key provided."

    pyautogui.press(key, presses=int(presses))
    sleep(CONFIG["after_hotkey_wait"])

    return f"Pressed {key}."


def hotkey(*keys: str) -> str:
    if not require_pyautogui():
        return "Keyboard control is not available."

    keys = [clean_text(key) for key in keys if clean_text(key)]

    if not keys:
        return "No keys provided."

    pyautogui.hotkey(*keys)
    sleep(CONFIG["after_hotkey_wait"])

    return "Pressed shortcut: " + " + ".join(keys)


def type_text(text: str, interval: float = 0.01) -> str:
    if not require_pyautogui():
        return "Typing control is not available."

    text = clean_text(text)

    if not text:
        return "No text provided."

    pyautogui.write(text, interval=float(interval))
    sleep(CONFIG["after_type_wait"])

    save_state({"last_action": "type_text", "last_text": text})

    return "Typed text."


def paste_text(text: str) -> str:
    text = clean_text(text)

    if not text:
        return "No text provided."

    if pyperclip and pyautogui:
        pyperclip.copy(text)
        sleep(0.05)
        pyautogui.hotkey("command", "v")
        sleep(CONFIG["after_type_wait"])

        save_state({"last_action": "paste_text", "last_text": text})

        return "Pasted text."

    return type_text(text)


def copy_selected_text() -> str:
    if not require_pyautogui():
        return ""

    pyautogui.hotkey("command", "c")
    sleep(0.15)

    if pyperclip:
        return pyperclip.paste()

    return ""


def select_all() -> str:
    return hotkey("command", "a")


def enter() -> str:
    return press("enter")


def escape() -> str:
    return press("esc")


def tab() -> str:
    return press("tab")


# =========================================================
# CLIPBOARD
# =========================================================
def set_clipboard(text: str) -> str:
    text = clean_text(text)

    if pyperclip:
        pyperclip.copy(text)
        return "Copied to clipboard."

    try:
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, text=True)
        process.communicate(text, timeout=3)
        return "Copied to clipboard."
    except Exception as error:
        return f"Could not copy to clipboard: {error}"


def get_clipboard() -> str:
    if pyperclip:
        try:
            return pyperclip.paste()
        except Exception:
            pass

    code, out, _ = run_command(["pbpaste"], timeout=3)

    if code == 0:
        return out

    return ""


# =========================================================
# SCREENSHOT
# =========================================================
def screenshot(path: Optional[str] = None) -> str:
    if not require_pyautogui():
        return "Screenshot control is not available."

    if not path:
        path = str(SCREENSHOT_DIR / f"screenshot_{int(time.time())}.png")

    img = pyautogui.screenshot()
    img.save(path)

    save_state({"last_action": "screenshot", "last_screenshot": path})

    return path


def screenshot_region(x: int, y: int, w: int, h: int, path: Optional[str] = None) -> str:
    if not require_pyautogui():
        return "Screenshot control is not available."

    if not path:
        path = str(SCREENSHOT_DIR / f"region_{int(time.time())}.png")

    img = pyautogui.screenshot(region=(int(x), int(y), int(w), int(h)))
    img.save(path)

    save_state({
        "last_action": "screenshot_region",
        "last_screenshot": path,
        "region": {"x": x, "y": y, "w": w, "h": h},
    })

    return path


def screenshot_front_window(path: Optional[str] = None) -> str:
    bounds = get_front_window_bounds()

    if not bounds:
        return screenshot(path)

    return screenshot_region(
        bounds["x"],
        bounds["y"],
        bounds["w"],
        bounds["h"],
        path=path,
    )


# =========================================================
# VOLUME / BRIGHTNESS
# =========================================================
def get_volume_number() -> int:
    script = "output volume of (get volume settings)"
    out = run_osascript(script)

    try:
        return int(float(out))
    except Exception:
        return 0


def get_volume() -> str:
    return f"{get_volume_number()}%"


def set_volume(level: int) -> str:
    try:
        level = int(level)
    except Exception:
        return "Invalid volume level."

    level = max(0, min(100, level))

    run_osascript(f"set volume output volume {level}")

    save_state({"last_action": "set_volume", "volume": level})

    return f"Volume set to {level}%."


def change_volume(delta: int) -> str:
    current = get_volume_number()

    try:
        delta = int(delta)
    except Exception:
        delta = 10

    new_level = max(0, min(100, current + delta))

    return set_volume(new_level)


def volume_up_percent(percent: int = 10) -> str:
    return change_volume(abs(int(percent)))


def volume_down_percent(percent: int = 10) -> str:
    return change_volume(-abs(int(percent)))


def mute() -> str:
    run_osascript("set volume with output muted")
    return "Muted volume."


def unmute() -> str:
    run_osascript("set volume without output muted")
    return "Unmuted volume."


def brightness_tool_path() -> str:
    candidates = [
        "/opt/homebrew/bin/brightness",
        "/usr/local/bin/brightness",
        shutil.which("brightness") or "",
    ]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate

    return ""


def set_brightness(level: float) -> str:
    tool = brightness_tool_path()

    if not tool:
        return "Brightness utility is not installed. Install it with: brew install brightness"

    try:
        level = float(level)
    except Exception:
        return "Invalid brightness level."

    if level > 1:
        level = level / 100

    level = max(0.0, min(1.0, level))

    code, _, err = run_command([tool, str(level)])

    if code == 0:
        return f"Brightness set to {int(level * 100)}%."

    return f"Could not set brightness: {err}"


# =========================================================
# SYSTEM SETTINGS / WIFI / BLUETOOTH
# =========================================================
SETTINGS_KEYWORDS = {
    "wifi": "Wi-Fi",
    "wi-fi": "Wi-Fi",
    "wife": "Wi-Fi",
    "bluetooth": "Bluetooth",
    "keyboard": "Keyboard",
    "trackpad": "Trackpad",
    "mouse": "Mouse",
    "display": "Displays",
    "screen": "Displays",
    "sound": "Sound",
    "privacy": "Privacy & Security",
    "security": "Privacy & Security",
    "battery": "Battery",
    "storage": "Storage",
    "icloud": "Apple ID",
    "apple id": "Apple ID",
    "wallpaper": "Wallpaper",
    "siri": "Siri & Spotlight",
    "spotlight": "Siri & Spotlight",
    "network": "Network",
    "accessibility": "Accessibility",
    "microphone": "Microphone",
    "camera": "Camera",
    "screen recording": "Screen Recording",
    "automation": "Automation",
    "input monitoring": "Input Monitoring",
}


def normalize_settings_query(query: str) -> str:
    query = compact_spaces(query)
    low = normalize(query)

    return SETTINGS_KEYWORDS.get(low, query)


def open_system_settings(query: str = "") -> str:
    query = normalize_settings_query(query)

    open_app("System Settings")
    sleep(CONFIG["settings_wait"])

    if query:
        search_system_settings(query)
        return f"Opened System Settings and searched for {query}."

    return "Opened System Settings."


def search_system_settings(query: str) -> str:
    query = normalize_settings_query(query)

    if not query:
        return open_system_settings()

    if not require_pyautogui():
        return "Keyboard control is not available."

    activate_app("System Settings")
    sleep(0.5)

    pyautogui.hotkey("command", "f")
    sleep(0.3)

    if pyperclip:
        pyperclip.copy(query)
        pyautogui.hotkey("command", "v")
    else:
        pyautogui.write(query, interval=0.01)

    sleep(0.5)

    save_state({
        "last_action": "search_system_settings",
        "query": query,
    })

    return f"Searched System Settings for {query}."


def open_wifi_settings() -> str:
    return open_system_settings("Wi-Fi")


def open_bluetooth_settings() -> str:
    return open_system_settings("Bluetooth")


def get_wifi_device() -> str:
    code, out, _ = run_command(["networksetup", "-listallhardwareports"])

    if code != 0 or not out:
        return ""

    lines = out.splitlines()

    for i, line in enumerate(lines):
        if "Hardware Port: Wi-Fi" in line or "Hardware Port: AirPort" in line:
            for j in range(i, min(i + 5, len(lines))):
                if lines[j].startswith("Device:"):
                    return lines[j].split(":", 1)[1].strip()

    return ""


def wifi_power(power: str) -> str:
    power = normalize(power)

    if power in ["on", "enable", "enabled", "true", "1"]:
        desired = "on"
    elif power in ["off", "disable", "disabled", "false", "0"]:
        desired = "off"
    else:
        return "Please say Wi-Fi on or Wi-Fi off."

    device = get_wifi_device()

    if not device:
        open_wifi_settings()
        return "I could not find the Wi-Fi device automatically, so I opened Wi-Fi settings."

    code, _, err = run_command(["networksetup", "-setairportpower", device, desired])

    if code == 0:
        save_state({"last_action": "wifi_power", "power": desired, "device": device})
        return f"Wi-Fi turned {desired}."

    open_wifi_settings()
    return f"I could not turn Wi-Fi {desired}: {err}. I opened Wi-Fi settings."


def wifi_status() -> str:
    device = get_wifi_device()

    if not device:
        return "I could not detect the Wi-Fi device."

    code, out, err = run_command(["networksetup", "-getairportpower", device])

    if code == 0:
        return out

    return f"Could not get Wi-Fi status: {err}"


def blueutil_path() -> str:
    candidates = [
        "/opt/homebrew/bin/blueutil",
        "/usr/local/bin/blueutil",
        shutil.which("blueutil") or "",
    ]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate

    return ""


def bluetooth_power(power: str) -> str:
    power = normalize(power)

    if power in ["on", "enable", "enabled", "true", "1"]:
        desired = "1"
        word = "on"
    elif power in ["off", "disable", "disabled", "false", "0"]:
        desired = "0"
        word = "off"
    else:
        return "Please say Bluetooth on or Bluetooth off."

    tool = blueutil_path()

    if not tool:
        open_bluetooth_settings()
        return "Bluetooth control needs blueutil. Install it with: brew install blueutil. I opened Bluetooth settings."

    code, _, err = run_command([tool, "--power", desired])

    if code == 0:
        save_state({"last_action": "bluetooth_power", "power": word})
        return f"Bluetooth turned {word}."

    open_bluetooth_settings()
    return f"I could not turn Bluetooth {word}: {err}. I opened Bluetooth settings."


def bluetooth_status() -> str:
    tool = blueutil_path()

    if not tool:
        open_bluetooth_settings()
        return "Bluetooth status needs blueutil. Install it with: brew install blueutil."

    code, out, err = run_command([tool, "--power"])

    if code != 0:
        return f"Could not get Bluetooth status: {err}"

    return "Bluetooth is on." if out.strip() == "1" else "Bluetooth is off."


# =========================================================
# FILES / FOLDERS / FINDER
# =========================================================
COMMON_LOCATIONS = {
    "desktop": Path.home() / "Desktop",
    "downloads": Path.home() / "Downloads",
    "download": Path.home() / "Downloads",
    "documents": Path.home() / "Documents",
    "document": Path.home() / "Documents",
    "home": Path.home(),
    "himora": Path.home() / "Desktop" / "Himora",
}


def resolve_common_location(location: str = "") -> Path:
    location = normalize(location)

    if not location:
        return Path.home() / "Desktop"

    if location in COMMON_LOCATIONS:
        return COMMON_LOCATIONS[location]

    expanded = Path(os.path.expanduser(location))

    if expanded.exists() or str(expanded).startswith("/"):
        return expanded

    return Path.home() / "Desktop"


def open_path(path: str) -> str:
    path = os.path.expanduser(clean_text(path))

    if not path:
        return "No path provided."

    code, _, err = run_command(["open", path])

    if code == 0:
        return f"Opened {path}."

    return f"Could not open path: {err}"


def reveal_in_finder(path: str) -> str:
    path = os.path.expanduser(clean_text(path))

    if not path:
        return "No path provided."

    code, _, err = run_command(["open", "-R", path])

    if code == 0:
        return f"Revealed {path} in Finder."

    return f"Could not reveal path: {err}"


def create_folder(name: str, location: str = "desktop") -> str:
    name = clean_text(name)

    if not name:
        return "No folder name provided."

    base = resolve_common_location(location)
    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)

    save_state({
        "last_action": "create_folder",
        "folder": str(folder),
    })

    return f"Created folder: {folder}"


def create_file(name: str, location: str = "desktop", content: str = "") -> str:
    name = clean_text(name)

    if not name:
        return "No file name provided."

    base = resolve_common_location(location)
    base.mkdir(parents=True, exist_ok=True)

    path = base / name
    path.write_text(content, encoding="utf-8")

    save_state({
        "last_action": "create_file",
        "file": str(path),
    })

    return f"Created file: {path}"


def mdfind_query(query: str, kind: str = "", limit: int = 10) -> List[str]:
    query = compact_spaces(query)

    if not query:
        return []

    if kind in ["folder", "directory"]:
        command = f'mdfind \'kMDItemFSName == "*{query}*"cd && kMDItemContentType == "public.folder"\''
    elif kind in ["app", "application"]:
        command = f'mdfind \'kMDItemFSName == "*{query}*"cd && kMDItemKind == "Application"\''
    else:
        command = f'mdfind \'kMDItemFSName == "*{query}*"cd || kMDItemDisplayName == "*{query}*"cd || kMDItemTextContent == "*{query}*"cd\''

    code, out, _ = run_shell(command, timeout=8)

    if code != 0 or not out:
        return []

    results = []

    for line in out.splitlines():
        line = line.strip()

        if line and Path(line).exists():
            results.append(line)

        if len(results) >= limit:
            break

    return results


def find_files(query: str, kind: str = "", limit: int = 10) -> List[str]:
    results = mdfind_query(query, kind=kind, limit=limit)

    if results:
        return results

    # Fallback slower search in common folders.
    roots = [
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.home() / "Documents",
    ]

    query_low = normalize(query)
    found = []

    for root in roots:
        if not root.exists():
            continue

        try:
            for path in root.rglob("*"):
                if query_low in normalize(path.name):
                    if kind in ["folder", "directory"] and not path.is_dir():
                        continue
                    if kind in ["file"] and not path.is_file():
                        continue

                    found.append(str(path))

                if len(found) >= limit:
                    return found

        except Exception:
            pass

    return found


def open_best_match(query: str, kind: str = "") -> str:
    results = find_files(query, kind=kind, limit=5)

    if not results:
        # If not found, open Finder search.
        finder_search(query)
        return f"I could not directly find {query}, so I searched it in Finder."

    best = results[0]
    open_path(best)

    save_state({
        "last_action": "open_best_match",
        "query": query,
        "path": best,
    })

    return f"Opened: {best}"


def reveal_best_match(query: str, kind: str = "") -> str:
    results = find_files(query, kind=kind, limit=5)

    if not results:
        finder_search(query)
        return f"I could not directly find {query}, so I searched it in Finder."

    best = results[0]
    reveal_in_finder(best)

    return f"Revealed: {best}"


def finder_search(query: str, location: str = "home") -> str:
    query = compact_spaces(query)

    if not query:
        return "No Finder search query provided."

    open_app("Finder")
    sleep(0.5)

    if not require_pyautogui():
        return "Finder opened, but keyboard control is not available."

    # Go to location first.
    base = resolve_common_location(location)

    if base.exists():
        run_command(["open", str(base)])
        sleep(0.5)

    pyautogui.hotkey("command", "f")
    sleep(0.3)

    if pyperclip:
        pyperclip.copy(query)
        pyautogui.hotkey("command", "v")
    else:
        pyautogui.write(query, interval=0.01)

    sleep(0.4)

    save_state({
        "last_action": "finder_search",
        "query": query,
        "location": str(base),
    })

    return f"Searched Finder for {query}."


def spotlight_search(query: str) -> str:
    return spotlight_open(query)


# =========================================================
# NOTIFICATIONS
# =========================================================
def notify(title: str, message: str = "") -> str:
    title = clean_text(title) or "Himora"
    message = clean_text(message)

    safe_title = title.replace('"', '\\"')
    safe_message = message.replace('"', '\\"')

    script = f'display notification "{safe_message}" with title "{safe_title}"'
    run_osascript(script)

    return "Notification sent."


# =========================================================
# HIGH-LEVEL EXECUTOR
# =========================================================
def execute_mac_action(action: str, params: Optional[Dict[str, Any]] = None) -> str:
    params = params or {}
    action = normalize(action)

    if action in ["open_app", "mac_open_app"]:
        return open_app(params.get("app", ""))

    if action in ["spotlight_open", "open_with_spotlight"]:
        return spotlight_open(params.get("query", ""))

    if action in ["activate_app", "mac_activate_app"]:
        return activate_app(params.get("app", ""))

    if action in ["close_app", "mac_close_app", "quit_app"]:
        return close_app(params.get("app", ""))

    if action in ["force_quit_app", "mac_force_quit_app"]:
        return force_quit_app(params.get("app", ""))

    if action in ["is_app_running"]:
        return str(is_app_running(params.get("app", "")))

    if action in ["frontmost_app", "get_frontmost_app"]:
        return get_frontmost_app()

    if action in ["list_running_apps"]:
        return ", ".join(list_running_apps())

    if action in ["open_url", "mac_open_url"]:
        return open_url(params.get("url", ""), params.get("browser"))

    if action in ["google_search", "search_google", "web_search"]:
        return google_search(params.get("query", ""), params.get("browser"))

    if action in ["youtube_search"]:
        return youtube_search(params.get("query", ""), params.get("browser"))

    if action in ["open_settings", "system_settings"]:
        return open_system_settings(params.get("query", ""))

    if action in ["search_settings"]:
        return search_system_settings(params.get("query", ""))

    if action in ["open_wifi_settings"]:
        return open_wifi_settings()

    if action in ["open_bluetooth_settings"]:
        return open_bluetooth_settings()

    if action in ["wifi_on", "turn_wifi_on"]:
        return wifi_power("on")

    if action in ["wifi_off", "turn_wifi_off"]:
        return wifi_power("off")

    if action in ["wifi_status"]:
        return wifi_status()

    if action in ["bluetooth_on", "turn_bluetooth_on"]:
        return bluetooth_power("on")

    if action in ["bluetooth_off", "turn_bluetooth_off"]:
        return bluetooth_power("off")

    if action in ["bluetooth_status"]:
        return bluetooth_status()

    if action in ["set_volume"]:
        return set_volume(params.get("level", 50))

    if action in ["volume_up", "increase_volume"]:
        return volume_up_percent(params.get("percent", params.get("amount", 10)))

    if action in ["volume_down", "decrease_volume"]:
        return volume_down_percent(params.get("percent", params.get("amount", 10)))

    if action in ["get_volume"]:
        return get_volume()

    if action in ["mute"]:
        return mute()

    if action in ["unmute"]:
        return unmute()

    if action in ["set_brightness"]:
        return set_brightness(params.get("level", 70))

    if action in ["create_folder"]:
        return create_folder(params.get("name", ""), params.get("location", "desktop"))

    if action in ["create_file"]:
        return create_file(params.get("name", ""), params.get("location", "desktop"), params.get("content", ""))

    if action in ["find_files", "search_files"]:
        results = find_files(params.get("query", ""), params.get("kind", ""), params.get("limit", 10))
        return "\n".join(results) if results else "No matching files found."

    if action in ["open_file", "open_folder", "open_best_match"]:
        return open_best_match(params.get("query", ""), params.get("kind", ""))

    if action in ["reveal_file", "reveal_folder", "reveal_best_match"]:
        return reveal_best_match(params.get("query", ""), params.get("kind", ""))

    if action in ["finder_search"]:
        return finder_search(params.get("query", ""), params.get("location", "home"))

    if action in ["open_path"]:
        return open_path(params.get("path", ""))

    if action in ["reveal_in_finder"]:
        return reveal_in_finder(params.get("path", ""))

    if action in ["click", "mac_click"]:
        return click(params.get("x", 0), params.get("y", 0), params.get("clicks", 1))

    if action in ["double_click"]:
        return double_click(params.get("x", 0), params.get("y", 0))

    if action in ["right_click"]:
        return right_click(params.get("x", 0), params.get("y", 0))

    if action in ["move_mouse"]:
        return move_mouse(params.get("x", 0), params.get("y", 0), params.get("duration", 0.2))

    if action in ["scroll", "mac_scroll"]:
        return scroll(params.get("amount", -5))

    if action in ["scroll_down"]:
        return scroll_down(params.get("amount", 5))

    if action in ["scroll_up"]:
        return scroll_up(params.get("amount", 5))

    if action in ["press", "mac_press"]:
        return press(params.get("key", ""), params.get("presses", 1))

    if action in ["hotkey", "mac_hotkey"]:
        keys = params.get("keys", [])

        if isinstance(keys, str):
            keys = [item.strip() for item in keys.split("+")]

        return hotkey(*keys)

    if action in ["type_text", "mac_type"]:
        return type_text(params.get("text", ""), params.get("interval", 0.01))

    if action in ["paste_text", "mac_paste"]:
        return paste_text(params.get("text", ""))

    if action in ["copy_selected_text"]:
        return copy_selected_text()

    if action in ["select_all"]:
        return select_all()

    if action in ["enter"]:
        return enter()

    if action in ["escape"]:
        return escape()

    if action in ["tab"]:
        return tab()

    if action in ["get_clipboard"]:
        return get_clipboard()

    if action in ["set_clipboard"]:
        return set_clipboard(params.get("text", ""))

    if action in ["screenshot"]:
        return screenshot(params.get("path"))

    if action in ["screenshot_region"]:
        return screenshot_region(
            params.get("x", 0),
            params.get("y", 0),
            params.get("w", 500),
            params.get("h", 500),
            params.get("path"),
        )

    if action in ["screenshot_front_window"]:
        return screenshot_front_window(params.get("path"))

    if action in ["notify"]:
        return notify(params.get("title", "Himora"), params.get("message", ""))

    if action in ["get_front_window_bounds"]:
        return json.dumps(get_front_window_bounds(), indent=2)

    if action in ["get_app_window_bounds"]:
        return json.dumps(get_app_window_bounds(params.get("app", "")), indent=2)

    if action in ["maximize_front_window"]:
        return maximize_front_window()

    if action in ["minimize_front_window"]:
        return minimize_front_window()

    if action in ["close_front_window"]:
        return close_front_window()

    return f"Unknown mac action: {action}"


# =========================================================
# DIRECT NATURAL TEST PARSER
# =========================================================
def parse_direct_command(command: str) -> Tuple[str, Dict[str, Any]]:
    command = compact_spaces(command)
    low = normalize(command)

    if low in ["front app", "current app"]:
        return "frontmost_app", {}

    if low == "bounds":
        return "get_front_window_bounds", {}

    if low == "screenshot":
        return "screenshot", {}

    if low == "mute":
        return "mute", {}

    if low == "unmute":
        return "unmute", {}

    if low in ["wifi on", "wi-fi on", "wife on", "turn wifi on", "turn wi-fi on"]:
        return "wifi_on", {}

    if low in ["wifi off", "wi-fi off", "wife off", "turn wifi off", "turn wi-fi off"]:
        return "wifi_off", {}

    if low in ["wifi status", "wi-fi status"]:
        return "wifi_status", {}

    if low in ["bluetooth on", "turn bluetooth on"]:
        return "bluetooth_on", {}

    if low in ["bluetooth off", "turn bluetooth off"]:
        return "bluetooth_off", {}

    if low in ["bluetooth status"]:
        return "bluetooth_status", {}

    if low in ["open wifi", "open wi-fi", "open wifi settings", "open wi-fi settings", "open wife"]:
        return "open_wifi_settings", {}

    if low in ["open bluetooth", "open bluetooth settings"]:
        return "open_bluetooth_settings", {}

    settings_match = re.search(r"^(?:open|search)\s+(?:settings|system settings)\s+(?:for\s+)?(.+)$", command, re.IGNORECASE)
    if settings_match:
        return "open_settings", {"query": settings_match.group(1).strip()}

    settings_match_2 = re.search(r"^open\s+(.+?)\s+settings$", command, re.IGNORECASE)
    if settings_match_2:
        return "open_settings", {"query": settings_match_2.group(1).strip()}

    set_volume_match = re.search(r"^(?:set\s+)?volume\s+(?:to\s+)?(\d+)\s*%?$", command, re.IGNORECASE)
    if set_volume_match:
        return "set_volume", {"level": int(set_volume_match.group(1))}

    volume_up_match = re.search(r"^(?:volume\s+up|increase\s+volume)(?:\s+by)?\s*(\d+)?\s*%?$", command, re.IGNORECASE)
    if volume_up_match:
        amount = int(volume_up_match.group(1) or 10)
        return "volume_up", {"percent": amount}

    volume_down_match = re.search(r"^(?:volume\s+down|decrease\s+volume)(?:\s+by)?\s*(\d+)?\s*%?$", command, re.IGNORECASE)
    if volume_down_match:
        amount = int(volume_down_match.group(1) or 10)
        return "volume_down", {"percent": amount}

    brightness_match = re.search(r"^(?:set\s+)?brightness\s+(?:to\s+)?(\d+)\s*%?$", command, re.IGNORECASE)
    if brightness_match:
        return "set_brightness", {"level": int(brightness_match.group(1))}

    create_folder_match = re.search(
        r"^(?:create|make)\s+(?:a\s+)?folder\s+(?:named\s+|called\s+)?(.+?)(?:\s+in\s+(desktop|downloads|documents|home|himora))?$",
        command,
        re.IGNORECASE,
    )
    if create_folder_match:
        return "create_folder", {
            "name": create_folder_match.group(1).strip(),
            "location": create_folder_match.group(2) or "desktop",
        }

    find_folder_match = re.search(r"^(?:find|search)\s+(?:folder|directory)\s+(.+)$", command, re.IGNORECASE)
    if find_folder_match:
        return "finder_search", {"query": find_folder_match.group(1).strip(), "location": "home"}

    open_folder_match = re.search(r"^(?:open)\s+(?:folder|directory)\s+(.+)$", command, re.IGNORECASE)
    if open_folder_match:
        return "open_best_match", {"query": open_folder_match.group(1).strip(), "kind": "folder"}

    find_file_match = re.search(r"^(?:find|search)\s+(?:file)\s+(.+)$", command, re.IGNORECASE)
    if find_file_match:
        return "finder_search", {"query": find_file_match.group(1).strip(), "location": "home"}

    open_file_match = re.search(r"^(?:open)\s+(?:file)\s+(.+)$", command, re.IGNORECASE)
    if open_file_match:
        return "open_best_match", {"query": open_file_match.group(1).strip(), "kind": "file"}

    search_finder_match = re.search(r"^search\s+finder\s+(?:for\s+)?(.+)$", command, re.IGNORECASE)
    if search_finder_match:
        return "finder_search", {"query": search_finder_match.group(1).strip(), "location": "home"}

    spotlight_match = re.search(r"^(?:spotlight|search spotlight)\s+(.+)$", command, re.IGNORECASE)
    if spotlight_match:
        return "spotlight_open", {"query": spotlight_match.group(1).strip()}

    if low.startswith("open "):
        target = command[5:].strip()

        if "." in target and " " not in target:
            return "open_url", {"url": target}

        return "open_app", {"app": target}

    if low.startswith("close "):
        return "close_app", {"app": command[6:].strip()}

    if low.startswith("activate "):
        return "activate_app", {"app": command[9:].strip()}

    if low.startswith("search "):
        return "google_search", {"query": command[7:].strip()}

    if low.startswith("youtube "):
        return "youtube_search", {"query": command[8:].strip()}

    if low.startswith("type "):
        return "type_text", {"text": command[5:].strip()}

    if low.startswith("paste "):
        return "paste_text", {"text": command[6:].strip()}

    if low.startswith("press "):
        return "press", {"key": command[6:].strip()}

    if low.startswith("hotkey "):
        keys = command[7:].strip().split("+")
        return "hotkey", {"keys": keys}

    if low.startswith("click "):
        parts = re.findall(r"-?\d+", command)

        if len(parts) >= 2:
            return "click", {"x": int(parts[0]), "y": int(parts[1])}

    if low.startswith("scroll down"):
        return "scroll_down", {"amount": 5}

    if low.startswith("scroll up"):
        return "scroll_up", {"amount": 5}

    return "unknown", {}


def run_direct_command(command: str) -> str:
    action, params = parse_direct_command(command)

    if action == "unknown":
        return "Unknown test command."

    log(f"Parsed direct command: {action} {params}")

    return execute_mac_action(action, params)


# =========================================================
# DIRECT TEST
# =========================================================
if __name__ == "__main__":
    print("=" * 60)
    print("HIMORA MAC SYSTEM TEST v2")
    print("=" * 60)
    print("Try:")
    print("- open whatsapp")
    print("- open any app name")
    print("- spotlight calculator")
    print("- volume 40")
    print("- volume up 20")
    print("- volume down 10")
    print("- wifi off")
    print("- wifi on")
    print("- bluetooth off")
    print("- bluetooth on")
    print("- open wifi settings")
    print("- open bluetooth settings")
    print("- open settings keyboard")
    print("- create folder Test Project in desktop")
    print("- find file main.py")
    print("- open file main.py")
    print("- find folder Himora")
    print("- open folder Himora")
    print("- search finder logo")
    print("- screenshot")
    print("- exit")
    print("=" * 60)

    while True:
        try:
            command = input("\nmac_system command: ").strip()

            if command.lower() in ["exit", "quit"]:
                break

            print(run_direct_command(command))

        except KeyboardInterrupt:
            print("\nStopped.")
            break

        except Exception as error:
            print("Error:", error)