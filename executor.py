"""
Himora executor.py - Final Advanced Bridge
------------------------------------------

This file is Himora's central execution bridge.

It connects:
- mac_system.py      -> Mac apps, files, settings, volume, Wi-Fi, Bluetooth
- whatsapp_agent.py  -> WhatsApp messaging/calling/replying
- youtube_agent.py   -> YouTube open/play/pause/resume/change
- gmail_agent.py     -> Gmail compose/open/send approval
- screen_agent.py    -> screen reading, OCR, errors, click visible text/buttons
- main.py            -> calls execute(task)

Important:
executor.py does NOT think deeply.
router.py and planner.py understand the command.
executor.py performs the action safely and reliably.
"""

import re
import json
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# =========================================================
# OPTIONAL IMPORTS
# =========================================================

try:
    from mac_system import execute_mac_action
    from mac_system import run_direct_command as run_mac_direct_command
except Exception as error:
    execute_mac_action = None
    run_mac_direct_command = None
    print(f"[EXECUTOR] mac_system import failed: {error}")


try:
    from whatsapp_agent import execute_whatsapp_action
    from whatsapp_agent import run_command as run_whatsapp_command
    from whatsapp_agent import handle_whatsapp_approval_command
except Exception as error:
    execute_whatsapp_action = None
    run_whatsapp_command = None
    handle_whatsapp_approval_command = None
    print(f"[EXECUTOR] whatsapp_agent import failed: {error}")


try:
    from youtube_agent import execute_youtube_action
except Exception as error:
    execute_youtube_action = None
    print(f"[EXECUTOR] youtube_agent execute import failed: {error}")


try:
    from youtube_agent import run_command as run_youtube_command
except Exception:
    run_youtube_command = None


try:
    from gmail_agent import execute_gmail_action
    from gmail_agent import handle_gmail_approval_command
except Exception as error:
    execute_gmail_action = None
    handle_gmail_approval_command = None
    print(f"[EXECUTOR] gmail_agent import failed: {error}")


try:
    from screen_agent import execute_screen_action
    from screen_agent import run_command as run_screen_command
except Exception as error:
    execute_screen_action = None
    run_screen_command = None
    print(f"[EXECUTOR] screen_agent import failed: {error}")


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory_data"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

EXECUTOR_STATE_FILE = MEMORY_DIR / "executor_state.json"


# =========================================================
# HELPERS
# =========================================================

def log(message: str):
    print(f"[EXECUTOR] {message}")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize(value: Any) -> str:
    return clean_text(value).lower()


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", clean_text(text)).strip()


def read_json(path: Path, default: Any):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass

    return default


def write_json(path: Path, data: Any) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except Exception as error:
        log(f"Could not write JSON: {error}")
        return False


def save_state(data: Dict[str, Any]):
    current = read_json(EXECUTOR_STATE_FILE, {})

    if not isinstance(current, dict):
        current = {}

    current.update(data)
    current["updated_at"] = time.time()

    write_json(EXECUTOR_STATE_FILE, current)


def safe_params(params: Any) -> Dict[str, Any]:
    if isinstance(params, dict):
        return params
    return {}


def result_text(result: Any) -> str:
    if result is None:
        return ""

    if isinstance(result, str):
        return result

    if isinstance(result, dict):
        try:
            return json.dumps(result, indent=2, ensure_ascii=False)
        except Exception:
            return str(result)

    if isinstance(result, list):
        return "\n".join(result_text(item) for item in result)

    return str(result)


# =========================================================
# COMMAND DETECTORS
# =========================================================

def is_coordinate_click(command: str) -> bool:
    return bool(re.search(r"^click\s+-?\d+\s+-?\d+$", command, re.IGNORECASE))


def is_screen_command(command: str) -> bool:
    low = normalize(command)

    if not low:
        return False

    exact = {
        "screenshot",
        "take screenshot",
        "capture screen",
        "screenshot window",
        "capture front window",
        "read screen",
        "read my screen",
        "read window",
        "read front window",
        "read current window",
        "describe screen",
        "describe my screen",
        "analyze screen",
        "look at screen",
        "look at my screen",
        "what is on my screen",
        "describe window",
        "analyze window",
        "look at current window",
        "find error",
        "read error",
        "check error",
        "check errors",
        "what error is on screen",
        "what is the error",
        "inspect ui",
        "show ui elements",
        "visible elements",
        "list buttons",
        "suggest next action",
        "what should i do next",
        "what next",
        "help me with this screen",
    }

    if low in exact:
        return True

    starts = (
        "click ",
        "tap ",
        "press ",
        "double click ",
        "force click ",
        "force double click ",
        "wait for ",
        "find text ",
        "find button ",
        "read screen",
        "describe screen",
        "analyze screen",
        "look at ",
    )

    if low.startswith(starts):
        # coordinate click should go to mac_system, not screen OCR.
        if is_coordinate_click(low):
            return False

        return True

    if "on screen" in low or "current window" in low or "front window" in low:
        return True

    return False


def is_whatsapp_command(command: str) -> bool:
    low = normalize(command)

    if not low:
        return False

    if any(word in low for word in ["whatsapp", "watsapp", "wotapp", "whats app"]):
        return True

    if low.startswith((
        "msg ",
        "message ",
        "text ",
        "reply ",
        "call ",
        "voice call ",
        "video call ",
    )):
        if "gmail" in low or "email" in low or "mail" in low:
            return False
        return True

    if low.startswith(("ask ", "write about ", "type about ", "reply about ")):
        return True

    if low in {
        "approve whatsapp bulk send",
        "approve bulk send",
        "send whatsapp bulk",
        "cancel whatsapp bulk",
        "show pending whatsapp",
    }:
        return True

    return False


def is_youtube_command(command: str) -> bool:
    low = normalize(command)

    if not low:
        return False

    if "youtube" in low or "you tube" in low:
        return True

    exact = {
        "pause the song",
        "resume the song",
        "change the song",
        "next song",
        "pause song",
        "resume song",
        "play song",
        "play music",
    }

    if low in exact:
        return True

    if low.startswith(("play ", "pause ", "resume ", "next ", "mute ", "unmute ")):
        if any(word in low for word in ["song", "music", "video"]):
            return True

    return False


def is_gmail_command(command: str) -> bool:
    low = normalize(command)

    if not low:
        return False

    if any(word in low for word in ["gmail", "email", "mail"]):
        return True

    if low.startswith(("compose ", "draft ")):
        return True

    if low in {
        "send it",
        "yes send it",
        "send email now",
        "discard email",
        "cancel email",
    }:
        return True

    return False


def is_mac_command(command: str) -> bool:
    low = normalize(command)

    if not low:
        return False

    starters = (
        "open ",
        "close ",
        "activate ",
        "launch ",
        "start ",
        "run ",
        "search ",
        "spotlight ",
        "volume ",
        "set volume",
        "increase volume",
        "decrease volume",
        "brightness ",
        "set brightness",
        "mute",
        "unmute",
        "wifi ",
        "wi-fi ",
        "wife ",
        "bluetooth ",
        "open settings",
        "open system settings",
        "open wifi",
        "open bluetooth",
        "create folder",
        "make folder",
        "create file",
        "find file",
        "find folder",
        "open file",
        "open folder",
        "search finder",
        "click ",
        "scroll ",
        "press ",
        "hotkey ",
        "type ",
        "paste ",
        "screenshot",
        "front app",
        "bounds",
    )

    return low.startswith(starters)


# =========================================================
# ACTION GROUPS
# =========================================================

SCREEN_ACTIONS = {
    "screen_screenshot",
    "screenshot_screen",
    "screen_screenshot_front_window",
    "screenshot_front_window",
    "screen_read",
    "read_screen",
    "ocr_screen",
    "screen_read_window",
    "read_front_window",
    "screen_errors",
    "read_errors",
    "find_errors",
    "screen_analyze",
    "analyze_screen",
    "describe_screen",
    "screen_suggest",
    "suggest_next_action",
    "screen_find_text",
    "find_text",
    "screen_click_text",
    "click_text",
    "click_button",
    "screen_double_click_text",
    "double_click_text",
    "screen_wait_for_text",
    "wait_for_text",
    "screen_click_and_type",
    "click_and_type",
    "screen_ui_elements",
    "inspect_ui",
    "visible_elements",
    "screen_from_command",
    "screen_command",
}

MAC_ACTIONS = {
    "open_app",
    "mac_open_app",
    "activate_app",
    "mac_activate_app",
    "close_app",
    "quit_app",
    "force_quit_app",
    "open_url",
    "mac_open_url",
    "google_search",
    "search_google",
    "web_search",
    "youtube_search",
    "open_settings",
    "system_settings",
    "search_settings",
    "open_wifi_settings",
    "open_bluetooth_settings",
    "wifi_on",
    "turn_wifi_on",
    "wifi_off",
    "turn_wifi_off",
    "wifi_status",
    "bluetooth_on",
    "turn_bluetooth_on",
    "bluetooth_off",
    "turn_bluetooth_off",
    "bluetooth_status",
    "set_volume",
    "volume_up",
    "increase_volume",
    "volume_down",
    "decrease_volume",
    "get_volume",
    "mute",
    "unmute",
    "set_brightness",
    "create_folder",
    "create_file",
    "find_files",
    "search_files",
    "open_file",
    "open_folder",
    "open_best_match",
    "reveal_file",
    "reveal_folder",
    "reveal_best_match",
    "finder_search",
    "spotlight_open",
    "open_with_spotlight",
    "open_path",
    "reveal_in_finder",
    "click",
    "mac_click",
    "double_click",
    "right_click",
    "move_mouse",
    "scroll",
    "mac_scroll",
    "scroll_down",
    "scroll_up",
    "press",
    "mac_press",
    "hotkey",
    "mac_hotkey",
    "type_text",
    "mac_type",
    "paste_text",
    "mac_paste",
    "copy_selected_text",
    "select_all",
    "enter",
    "escape",
    "tab",
    "get_clipboard",
    "set_clipboard",
    "screenshot",
    "screenshot_region",
    "notify",
    "get_front_window_bounds",
    "get_app_window_bounds",
    "maximize_front_window",
    "minimize_front_window",
    "close_front_window",
    "frontmost_app",
    "get_frontmost_app",
    "list_running_apps",
}


# =========================================================
# ACTION NORMALIZER
# =========================================================

def normalize_action_and_params(action: str, params: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    action = normalize(action)
    params = dict(params or {})

    if action == "open_website":
        action = "open_url"
        if "website" in params and "url" not in params:
            params["url"] = params["website"]

    elif action in ["search_web", "browser_search"]:
        action = "google_search"
        if "text" in params and "query" not in params:
            params["query"] = params["text"]

    elif action == "open_browser":
        action = "open_app"
        params["app"] = params.get("browser", "Google Chrome")

    elif action in ["type", "write_text"]:
        action = "type_text"
        if "content" in params and "text" not in params:
            params["text"] = params["content"]

    elif action in ["paste", "paste_clipboard"]:
        action = "paste_text"
        if "content" in params and "text" not in params:
            params["text"] = params["content"]

    elif action == "press_key":
        action = "press"
        if "key_name" in params and "key" not in params:
            params["key"] = params["key_name"]

    elif action in ["keyboard_shortcut", "shortcut"]:
        action = "hotkey"

    elif action in ["search_file", "find_file"]:
        action = "finder_search"
        if "name" in params and "query" not in params:
            params["query"] = params["name"]

    elif action in ["make_folder", "new_folder"]:
        action = "create_folder"

    elif action == "open_system_settings":
        action = "open_settings"

    elif action == "turn_wifi_on":
        action = "wifi_on"

    elif action == "turn_wifi_off":
        action = "wifi_off"

    elif action == "turn_bluetooth_on":
        action = "bluetooth_on"

    elif action == "turn_bluetooth_off":
        action = "bluetooth_off"

    elif action == "set_volume_percent":
        action = "set_volume"

    elif action == "volume_up_percent":
        action = "volume_up"

    elif action == "volume_down_percent":
        action = "volume_down"

    # Screen aliases
    elif action in ["read_my_screen", "screen_ocr"]:
        action = "screen_read"

    elif action in ["describe_my_screen", "look_at_screen"]:
        action = "screen_analyze"

    elif action in ["find_error", "read_error", "check_error"]:
        action = "screen_errors"

    elif action in ["click_visible_text", "click_visible_button"]:
        action = "screen_click_text"

    return action, params


# =========================================================
# NATURAL COMMAND EXECUTION
# =========================================================

def execute_natural_command(command: str) -> str:
    command = compact_spaces(command)

    if not command:
        return "No command provided."

    low = normalize(command)
    log(f"Natural command: {command}")

    # Gmail approval first.
    if handle_gmail_approval_command:
        try:
            approval = handle_gmail_approval_command(command)
            if approval:
                save_state({"last_route": "gmail_approval", "last_command": command})
                return result_text(approval)
        except Exception as error:
            log(f"Gmail approval handler failed: {error}")

    # WhatsApp approval first.
    if handle_whatsapp_approval_command:
        try:
            approval = handle_whatsapp_approval_command(command)
            if approval:
                save_state({"last_route": "whatsapp_approval", "last_command": command})
                return result_text(approval)
        except Exception as error:
            log(f"WhatsApp approval handler failed: {error}")

    # Screen commands before Mac commands, because "click Continue"
    # should use OCR, while "click 100 200" should use mac_system.
    if is_screen_command(command):
        if run_screen_command:
            save_state({"last_route": "screen", "last_command": command})
            return result_text(run_screen_command(command))

        return "Screen agent is not available."

    # WhatsApp
    if is_whatsapp_command(command):
        if run_whatsapp_command:
            save_state({"last_route": "whatsapp", "last_command": command})
            return result_text(run_whatsapp_command(command))

        return "WhatsApp agent is not available."

    # Gmail
    if is_gmail_command(command):
        if execute_gmail_action:
            save_state({"last_route": "gmail", "last_command": command})

            if low in ["open gmail", "gmail", "open email", "open mail"]:
                return result_text(execute_gmail_action("gmail_open", {}))

            return result_text(
                execute_gmail_action(
                    "gmail_compose_from_command",
                    {"command": command},
                )
            )

        return "Gmail agent is not available."

    # YouTube
    if is_youtube_command(command):
        save_state({"last_route": "youtube", "last_command": command})

        if run_youtube_command:
            return result_text(run_youtube_command(command))

        if execute_youtube_action:
            return result_text(
                execute_youtube_action(
                    "youtube_from_command",
                    {"command": command},
                )
            )

        return "YouTube agent is not available."

    # Mac/System
    if is_mac_command(command):
        if run_mac_direct_command:
            save_state({"last_route": "mac_direct", "last_command": command})
            return result_text(run_mac_direct_command(command))

        if execute_mac_action:
            if low.startswith("open "):
                target = command[5:].strip()
                return result_text(execute_mac_action("open_app", {"app": target}))

        return "Mac system controller is not available."

    return "I understood the command, but no executor route matched it yet."


# =========================================================
# STEP EXECUTION
# =========================================================

def execute_step(step: Dict[str, Any]) -> str:
    if not isinstance(step, dict):
        return ""

    action = clean_text(step.get("action") or step.get("name") or "")
    params = safe_params(step.get("params") or step.get("arguments") or {})

    if not action and "command" in step:
        action = "natural_command"
        params = {"command": step.get("command", "")}

    if not action:
        return "No action specified."

    action, params = normalize_action_and_params(action, params)

    log(f"Executing action: {action} params={params}")

    if action in ["direct_response", "respond", "say"]:
        return clean_text(params.get("response") or params.get("text") or "")

    if action in ["natural_command", "command", "execute_command", "from_command"]:
        return execute_natural_command(
            params.get("command", "")
            or params.get("text", "")
            or params.get("input", "")
        )

    # Screen
    if action in ["screen_from_command", "screen_command"]:
        command = (
            params.get("command", "")
            or params.get("text", "")
            or params.get("input", "")
        )

        if run_screen_command:
            return result_text(run_screen_command(command))

        return "Screen agent is not available."

    if action in SCREEN_ACTIONS or action.startswith("screen_"):
        if execute_screen_action:
            return result_text(execute_screen_action(action, params))

        return "Screen agent is not available."

    # WhatsApp
    if action in ["whatsapp_from_command", "whatsapp_command"]:
        command = (
            params.get("command", "")
            or params.get("text", "")
            or params.get("input", "")
        )

        if run_whatsapp_command:
            return result_text(run_whatsapp_command(command))

        return "WhatsApp agent is not available."

    if action.startswith("whatsapp_"):
        if execute_whatsapp_action:
            return result_text(execute_whatsapp_action(action, params))

        return "WhatsApp agent is not available."

    # Gmail
    if action in ["gmail_from_command", "email_from_command"]:
        command = (
            params.get("command", "")
            or params.get("text", "")
            or params.get("input", "")
        )

        if execute_gmail_action:
            return result_text(
                execute_gmail_action(
                    "gmail_compose_from_command",
                    {"command": command},
                )
            )

        return "Gmail agent is not available."

    if action.startswith("gmail_"):
        if execute_gmail_action:
            return result_text(execute_gmail_action(action, params))

        return "Gmail agent is not available."

    # YouTube
    if action in ["youtube_from_command", "youtube_command"]:
        command = (
            params.get("command", "")
            or params.get("text", "")
            or params.get("input", "")
        )

        if run_youtube_command:
            return result_text(run_youtube_command(command))

        if execute_youtube_action:
            return result_text(execute_youtube_action(action, params))

        return "YouTube agent is not available."

    if action.startswith("youtube_"):
        if execute_youtube_action:
            return result_text(execute_youtube_action(action, params))

        return "YouTube agent is not available."

    # Mac/System
    if action in MAC_ACTIONS or action.startswith("mac_"):
        if execute_mac_action:
            return result_text(execute_mac_action(action, params))

        return "Mac system controller is not available."

    # Legacy open fallback.
    if action == "open":
        target = params.get("target") or params.get("app") or params.get("url") or ""

        if not target:
            return "No target provided."

        if "." in target and execute_mac_action:
            return result_text(execute_mac_action("open_url", {"url": target}))

        if execute_mac_action:
            return result_text(execute_mac_action("open_app", {"app": target}))

    return f"Unknown action: {action}"


# =========================================================
# MAIN EXECUTE API
# =========================================================

def execute(task: Any) -> str:
    """
    Main function used by main.py.

    Accepts:
    1. String:
       execute("read my screen")

    2. Single task:
       execute({
           "type": "single",
           "action": "screen_read",
           "params": {}
       })

    3. Multi task:
       execute({
           "type": "multi",
           "steps": [...]
       })

    4. List of steps:
       execute([
           {"action": "open_app", "params": {"app": "Calculator"}}
       ])
    """

    try:
        if task is None:
            return ""

        if isinstance(task, str):
            return execute_natural_command(task)

        if isinstance(task, list):
            return execute_steps(task)

        if not isinstance(task, dict):
            return str(task)

        task_type = normalize(task.get("type", ""))

        if task_type in ["multi", "steps", "workflow"] or "steps" in task:
            steps = task.get("steps", [])

            if not isinstance(steps, list):
                return "Invalid steps format."

            return execute_steps(steps)

        if "action" in task or "command" in task:
            return execute_step(task)

        return "Invalid task format."

    except Exception as error:
        log(f"Execution error: {error}")
        traceback.print_exc()
        return f"Execution failed: {error}"


def execute_steps(steps: List[Dict[str, Any]]) -> str:
    results = []

    for index, current_step in enumerate(steps, start=1):
        try:
            result = execute_step(current_step)
            result = clean_text(result)

            if result:
                results.append(result)

        except Exception as error:
            log(f"Step {index} failed: {error}")
            results.append(f"Step {index} failed: {error}")

    if not results:
        return "Done."

    if len(results) == 1:
        return results[0]

    return "\n".join(results)


# =========================================================
# COMPATIBILITY ALIASES
# =========================================================

def execute_task(task: Any) -> str:
    return execute(task)


def run_task(task: Any) -> str:
    return execute(task)


def run(command: str) -> str:
    return execute(command)


# =========================================================
# DIRECT TEST
# =========================================================

if __name__ == "__main__":
    print("=" * 60)
    print("HIMORA EXECUTOR TEST - FINAL")
    print("=" * 60)
    print("Try:")
    print("- read my screen")
    print("- describe screen")
    print("- find error")
    print("- inspect ui")
    print("- click Continue")
    print("- what should i do next")
    print("- volume 40")
    print("- open bluetooth settings")
    print("- open youtube and play shape of you")
    print("- open gmail")
    print("- msg dad hello")
    print("- exit")
    print("=" * 60)               
    while True:
        try:
            command = input("\nexecutor command: ").strip()

            if command.lower() in ["exit", "quit"]:
                break

            print(execute(command))

        except KeyboardInterrupt:
            print("\nStopped.")
            break

        except Exception as error:
            print("Error:", error)