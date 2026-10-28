"""
Himora Advanced YouTube Agent - Direct Play + Background Control
---------------------------------------------------------------

This agent opens YouTube in the user's normal logged-in Google Chrome account.

Main features:
- Open YouTube
- Search YouTube
- Directly resolve first video and open it
- Avoid accidental auto-pause
- Pause / resume / next / previous / mute / fullscreen
- Change song
- Play another song
- Natural command parser for background voice commands

Important:
This file alone handles YouTube.
For Himora background voice to control it, executor.py must call this agent.
That integration comes after this file is tested.

No guest Chrome.
No Playwright guest profile.
"""

import re
import time
import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import quote_plus


try:
    import pyautogui
except Exception:
    pyautogui = None


# =========================================================
# PATHS
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory_data"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

YOUTUBE_STATE_FILE = MEMORY_DIR / "youtube_state.json"


# =========================================================
# CONFIG
# =========================================================
CHROME_APP_NAME = "Google Chrome"

YOUTUBE_HOME = "https://www.youtube.com"
YOUTUBE_SEARCH = "https://www.youtube.com/results?search_query="
YOUTUBE_WATCH = "https://www.youtube.com/watch?v="

CONFIG = {
    "wait_after_open": 2.0,
    "wait_after_search": 2.0,
    "wait_after_video_open": 2.4,
    "request_timeout": 12,
}


# =========================================================
# LOGGER
# =========================================================
def log(message: str):
    print(f"[YOUTUBE AGENT] {message}")


# =========================================================
# BASIC HELPERS
# =========================================================
def clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize(value) -> str:
    return clean_text(value).lower()


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", clean_text(text)).strip()


def sleep(seconds: float):
    time.sleep(seconds)


def search_url(query: str) -> str:
    return YOUTUBE_SEARCH + quote_plus(clean_text(query))


def watch_url(video_id: str) -> str:
    return YOUTUBE_WATCH + clean_text(video_id)


def read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass

    return default


def write_json(path: Path, data) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except Exception as error:
        log(f"Failed to write state: {error}")
        return False


# =========================================================
# STATE
# =========================================================
def save_youtube_state(data: Dict[str, Any]):
    current = read_json(YOUTUBE_STATE_FILE, {})
    current.update(data)
    current["updated_at"] = time.time()
    write_json(YOUTUBE_STATE_FILE, current)


def load_youtube_state() -> Dict[str, Any]:
    return read_json(YOUTUBE_STATE_FILE, {})


def youtube_is_active() -> bool:
    state = load_youtube_state()
    return bool(state.get("active"))


def last_query() -> str:
    state = load_youtube_state()
    return clean_text(state.get("last_query", ""))


# =========================================================
# CHROME CONTROL
# =========================================================
def activate_chrome() -> bool:
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'tell application "{CHROME_APP_NAME}" to activate',
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def open_url_in_chrome(url: str) -> bool:
    url = clean_text(url)

    if not url:
        return False

    try:
        subprocess.run(
            ["open", "-a", CHROME_APP_NAME, url],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        activate_chrome()
        return True

    except Exception as error:
        log(f"Failed to open Chrome URL: {error}")
        return False


def chrome_execute_js(js_code: str) -> str:
    """
    Executes JavaScript in the active Chrome tab.

    Stronger controls need:
    Chrome menu bar → View → Developer → Allow JavaScript from Apple Events
    """
    js_code = clean_text(js_code)

    if not js_code:
        return ""

    apple_script = f'''
    tell application "{CHROME_APP_NAME}"
        activate
        if (count of windows) is 0 then
            make new window
        end if
        tell active tab of front window
            execute javascript {json.dumps(js_code)}
        end tell
    end tell
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", apple_script],
            check=False,
            capture_output=True,
            text=True,
        )

        return clean_text(result.stdout)

    except Exception:
        return ""


def chrome_js_available() -> bool:
    result = chrome_execute_js("(() => 'himora_js_ok')();")
    return "himora_js_ok" in result


# =========================================================
# YOUTUBE VIDEO RESOLVER
# =========================================================
def fetch_youtube_search_html(query: str) -> str:
    url = search_url(query)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    request = urllib.request.Request(
        url,
        headers=headers,
    )

    with urllib.request.urlopen(
        request,
        timeout=CONFIG["request_timeout"],
    ) as response:
        html = response.read().decode(
            "utf-8",
            errors="ignore",
        )

    return html


def extract_video_ids(html: str) -> list[str]:
    if not html:
        return []

    patterns = [
        r'"videoId":"([a-zA-Z0-9_-]{11})"',
        r"watch\?v=([a-zA-Z0-9_-]{11})",
        r"/watch\?v=([a-zA-Z0-9_-]{11})",
    ]

    found = []

    for pattern in patterns:
        found.extend(re.findall(pattern, html))

    clean_ids = []
    seen = set()

    for video_id in found:
        if len(video_id) != 11:
            continue

        if video_id in seen:
            continue

        seen.add(video_id)
        clean_ids.append(video_id)

    return clean_ids


def resolve_first_video_id(query: str) -> Optional[str]:
    query = clean_text(query)

    if not query:
        return None

    try:
        log(f"Resolving first YouTube video for: {query}")

        html = fetch_youtube_search_html(query)
        video_ids = extract_video_ids(html)

        if video_ids:
            log(f"First video ID: {video_ids[0]}")
            return video_ids[0]

    except Exception as error:
        log(f"Direct video resolve failed: {error}")

    return None


# =========================================================
# VIDEO CONTROL HELPERS
# =========================================================
def keyboard_space_toggle() -> bool:
    if pyautogui is None:
        return False

    try:
        activate_chrome()
        sleep(0.3)
        pyautogui.press("space")
        return True
    except Exception:
        return False


def keyboard_hotkey(*keys) -> bool:
    if pyautogui is None:
        return False

    try:
        activate_chrome()
        sleep(0.2)
        pyautogui.hotkey(*keys)
        return True
    except Exception:
        return False


def keyboard_key(key: str) -> bool:
    if pyautogui is None:
        return False

    try:
        activate_chrome()
        sleep(0.2)
        pyautogui.press(key)
        return True
    except Exception:
        return False


def get_video_state() -> str:
    js = """
    (() => {
        const video = document.querySelector('video');
        if (!video) return 'no_video';

        if (video.paused) return 'paused';
        return 'playing';
    })();
    """

    result = chrome_execute_js(js)

    if "playing" in result:
        return "playing"

    if "paused" in result:
        return "paused"

    return "unknown"


def force_play_video() -> bool:
    """
    Tries to play video without using Space.
    This avoids accidental pause.
    """
    js = """
    (() => {
        const video = document.querySelector('video');
        if (!video) return 'no_video';

        video.play();
        return video.paused ? 'still_paused' : 'playing';
    })();
    """

    result = chrome_execute_js(js)

    if "playing" in result:
        return True

    return False


def force_pause_video() -> bool:
    js = """
    (() => {
        const video = document.querySelector('video');
        if (!video) return 'no_video';

        video.pause();
        return video.paused ? 'paused' : 'still_playing';
    })();
    """

    result = chrome_execute_js(js)

    if "paused" in result:
        return True

    return False


def toggle_play_pause() -> str:
    state = get_video_state()

    if state == "playing":
        if force_pause_video():
            save_youtube_state({
                "playing": False,
                "last_action": "youtube_pause",
            })
            return "Paused the song."

    if state == "paused":
        if force_play_video():
            save_youtube_state({
                "playing": True,
                "last_action": "youtube_play",
            })
            return "Playing the song."

    # fallback only for manual pause/play command
    if keyboard_space_toggle():
        state_after = get_video_state()

        if state_after == "playing":
            save_youtube_state({"playing": True})
            return "Playing the song."

        if state_after == "paused":
            save_youtube_state({"playing": False})
            return "Paused the song."

        return "Toggled play or pause."

    return "I could not control play or pause."


def ensure_playing_after_open():
    """
    Important:
    Do NOT press space here.
    Space caused the previous auto-stop problem.

    We only call JS play if available.
    If JS is not allowed, we leave YouTube's natural autoplay alone.
    """
    force_play_video()


# =========================================================
# YOUTUBE AGENT
# =========================================================
class YouTubeAgent:
    def open_youtube(self) -> str:
        log("Opening YouTube")

        open_url_in_chrome(YOUTUBE_HOME)
        sleep(CONFIG["wait_after_open"])

        save_youtube_state({
            "active": True,
            "last_action": "open_youtube",
            "last_query": "",
            "playing": False,
            "browser": "logged_in_chrome",
        })

        return "Opening YouTube."

    def search(self, query: str) -> str:
        query = clean_text(query)

        if not query:
            return "What should I search on YouTube?"

        log(f"Searching YouTube: {query}")

        url = search_url(query)

        open_url_in_chrome(url)
        sleep(CONFIG["wait_after_search"])

        save_youtube_state({
            "active": True,
            "last_action": "youtube_search",
            "last_query": query,
            "last_url": url,
            "playing": False,
            "browser": "logged_in_chrome",
        })

        return f"Searching YouTube for {query}."

    def search_and_play(self, query: str) -> str:
        query = clean_text(query)

        if not query:
            return "What should I play on YouTube?"

        log(f"Search and play: {query}")

        video_id = resolve_first_video_id(query)

        if video_id:
            direct_url = watch_url(video_id)

            open_url_in_chrome(direct_url)
            sleep(CONFIG["wait_after_video_open"])

            ensure_playing_after_open()

            save_youtube_state({
                "active": True,
                "last_action": "youtube_search_and_play_direct",
                "last_query": query,
                "last_url": direct_url,
                "last_video_id": video_id,
                "playing": True,
                "browser": "logged_in_chrome",
            })

            return f"Playing {query} on YouTube."

        url = search_url(query)

        open_url_in_chrome(url)
        sleep(CONFIG["wait_after_search"])

        save_youtube_state({
            "active": True,
            "last_action": "youtube_search_only",
            "last_query": query,
            "last_url": url,
            "playing": False,
            "browser": "logged_in_chrome",
        })

        return f"I searched YouTube for {query}, but I could not start the video."

    def play_first_result(self) -> str:
        query = last_query()

        if query:
            return self.search_and_play(query)

        return "I do not know what to play yet."

    def pause(self) -> str:
        state = get_video_state()

        if state == "playing":
            if force_pause_video():
                save_youtube_state({
                    "playing": False,
                    "last_action": "youtube_pause",
                })
                return "Paused the song."

        if state == "paused":
            save_youtube_state({
                "playing": False,
                "last_action": "youtube_pause",
            })
            return "The song is already paused."

        if keyboard_space_toggle():
            save_youtube_state({
                "playing": False,
                "last_action": "youtube_pause_keyboard",
            })
            return "Paused the song."

        return "I could not pause the song."

    def resume(self) -> str:
        state = get_video_state()

        if state == "paused":
            if force_play_video():
                save_youtube_state({
                    "playing": True,
                    "last_action": "youtube_resume",
                })
                return "Resumed the song."

        if state == "playing":
            save_youtube_state({
                "playing": True,
                "last_action": "youtube_resume",
            })
            return "The song is already playing."

        if keyboard_space_toggle():
            save_youtube_state({
                "playing": True,
                "last_action": "youtube_resume_keyboard",
            })
            return "Resumed the song."

        return "I could not resume the song."

    def toggle(self) -> str:
        return toggle_play_pause()

    def next_video(self) -> str:
        log("Next song")

        ok = keyboard_hotkey("shift", "n")

        if ok:
            save_youtube_state({
                "last_action": "youtube_next",
                "playing": True,
            })
            return "Playing the next song."

        return "I could not change the song."

    def previous_video(self) -> str:
        log("Previous song")

        ok = keyboard_hotkey("shift", "p")

        if ok:
            save_youtube_state({
                "last_action": "youtube_previous",
            })
            return "Going to the previous song."

        return "I could not go to the previous song."

    def change_song(self, query: str = "") -> str:
        query = clean_text(query)

        if query:
            return self.search_and_play(query)

        return self.next_video()

    def mute(self) -> str:
        ok = keyboard_key("m")

        if ok:
            save_youtube_state({
                "last_action": "youtube_mute",
            })
            return "Toggled mute on YouTube."

        return "I could not mute YouTube."

    def fullscreen(self) -> str:
        ok = keyboard_key("f")

        if ok:
            save_youtube_state({
                "last_action": "youtube_fullscreen",
            })
            return "Toggled fullscreen."

        return "I could not toggle fullscreen."

    def close(self) -> str:
        activate_chrome()

        if pyautogui:
            pyautogui.hotkey("command", "w")

        save_youtube_state({
            "active": False,
            "last_action": "youtube_close",
            "playing": False,
        })

        return "Closed YouTube."


# =========================================================
# SINGLETON
# =========================================================
youtube_agent = YouTubeAgent()


# =========================================================
# EXECUTOR HELPER
# =========================================================
def execute_youtube_action(action: str, params: Optional[Dict[str, Any]] = None) -> str:
    params = params or {}
    action = clean_text(action)

    query = (
        params.get("query")
        or params.get("text")
        or params.get("target")
        or ""
    )

    if action in ["youtube_open", "open_youtube"]:
        return youtube_agent.open_youtube()

    if action in ["youtube_search", "search_youtube"]:
        return youtube_agent.search(query)

    if action in ["youtube_search_and_play", "youtube_play_query", "play_youtube"]:
        return youtube_agent.search_and_play(query)

    if action in ["youtube_play_first", "play_first_youtube"]:
        return youtube_agent.play_first_result()

    if action in ["youtube_pause", "pause_song", "pause_youtube"]:
        return youtube_agent.pause()

    if action in ["youtube_resume", "resume_song", "play_song"]:
        return youtube_agent.resume()

    if action in ["youtube_toggle", "youtube_play_pause"]:
        return youtube_agent.toggle()

    if action in ["youtube_next", "next_youtube", "change_song"]:
        return youtube_agent.next_video()

    if action in ["youtube_previous", "previous_youtube"]:
        return youtube_agent.previous_video()

    if action in ["youtube_change_to", "play_another_song"]:
        return youtube_agent.change_song(query)

    if action in ["youtube_mute", "mute_youtube"]:
        return youtube_agent.mute()

    if action in ["youtube_fullscreen", "fullscreen_youtube"]:
        return youtube_agent.fullscreen()

    if action in ["youtube_close", "close_youtube"]:
        return youtube_agent.close()

    return f"Unknown YouTube action: {action}"


# =========================================================
# NATURAL COMMAND PARSER
# =========================================================
def parse_youtube_command(command: str) -> Dict[str, Any]:
    raw = compact_spaces(command)
    low = normalize(raw)

    if low in ["open youtube", "open yt", "youtube", "yt"]:
        return {
            "action": "youtube_open",
            "params": {},
        }

    patterns = [
        r"^open\s+(?:youtube|yt|you tube)\s+and\s+play\s+(.+)$",
        r"^play\s+(.+?)\s+on\s+(?:youtube|yt|you tube)$",
        r"^(?:youtube|yt|you tube)\s+play\s+(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, low, re.IGNORECASE)

        if match:
            return {
                "action": "youtube_search_and_play",
                "params": {
                    "query": match.group(1).strip(),
                },
            }

    if low.startswith("search "):
        query = raw[7:].strip()
        query = (
            query.replace("on youtube", "")
            .replace("youtube", "")
            .replace("yt", "")
            .strip()
        )

        return {
            "action": "youtube_search",
            "params": {
                "query": query,
            },
        }

    if low in [
        "pause",
        "pause song",
        "pause the song",
        "pause music",
        "stop song",
        "stop the song",
    ]:
        return {
            "action": "youtube_pause",
            "params": {},
        }

    if low in [
        "resume",
        "resume song",
        "resume the song",
        "play",
        "play song",
        "play the song",
        "continue",
    ]:
        return {
            "action": "youtube_resume",
            "params": {},
        }

    if low in [
        "next",
        "next song",
        "change song",
        "change the song",
        "play next",
        "next video",
    ]:
        return {
            "action": "youtube_next",
            "params": {},
        }

    change_patterns = [
        r"^change\s+(?:song|music)\s+to\s+(.+)$",
        r"^play\s+another\s+song\s+(.+)$",
        r"^play\s+another\s+music\s+(.+)$",
        r"^play\s+(.+)$",
    ]

    for pattern in change_patterns:
        match = re.search(pattern, low, re.IGNORECASE)

        if match:
            query = match.group(1).strip()

            return {
                "action": "youtube_change_to",
                "params": {
                    "query": query,
                },
            }

    if low in ["previous", "previous song", "back song", "previous video"]:
        return {
            "action": "youtube_previous",
            "params": {},
        }

    if low in ["mute", "unmute", "mute youtube"]:
        return {
            "action": "youtube_mute",
            "params": {},
        }

    if low in ["fullscreen", "full screen"]:
        return {
            "action": "youtube_fullscreen",
            "params": {},
        }

    if low in ["close youtube", "close song", "close music"]:
        return {
            "action": "youtube_close",
            "params": {},
        }

    return {
        "action": "youtube_search",
        "params": {
            "query": raw,
        },
    }


def run_command(command: str) -> str:
    parsed = parse_youtube_command(command)
    return execute_youtube_action(
        parsed["action"],
        parsed["params"],
    )


# =========================================================
# DEBUG
# =========================================================
if __name__ == "__main__":
    print("=" * 60)
    print("HIMORA YOUTUBE AGENT TEST - CONTROL MODE")
    print("=" * 60)
    print("Examples:")
    print("- open youtube")
    print("- open youtube and play shape of you")
    print("- pause the song")
    print("- resume the song")
    print("- change the song")
    print("- play another song believer")
    print("- mute")
    print("- fullscreen")
    print("- exit")
    print("=" * 60)

    while True:
        try:
            command = input("\nYouTube command: ").strip()

            if command.lower() in ["exit", "quit"]:
                break

            print(run_command(command))

        except KeyboardInterrupt:
            print("\nStopped.")
            break

        except Exception as error:
            print("Error:", error)