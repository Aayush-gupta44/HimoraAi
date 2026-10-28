"""
Himora planner.py v3
--------------------

Advanced planning layer for Himora.

Purpose:
- Understand messy voice/text commands.
- Convert them into executor-friendly task JSON.
- Support Mac system commands, WhatsApp, YouTube, Gmail, Finder, files, settings, volume, Wi-Fi, Bluetooth.
- Keep chat separate from actions.
- Provide compatibility functions for older Himora files:
    - plan()
    - expand_task()
    - create_plan()
    - follow_up()
    - is_action_request()

Important:
planner.py does NOT execute actions.
executor.py executes actions.

Flow:
User command -> router.py cleans voice -> planner.py creates task -> executor.py executes task
"""

import os
import re
import json
import time
import traceback
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


# =========================================================
# OPTIONAL ROUTER IMPORT
# =========================================================
try:
    from router import route_input, canonicalize_command, normalize_voice_text
except Exception:
    route_input = None
    canonicalize_command = None
    normalize_voice_text = None


# =========================================================
# PATHS / CONFIG
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory_data"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

PLANNER_STATE_FILE = MEMORY_DIR / "planner_state.json"
PLANNER_HISTORY_FILE = MEMORY_DIR / "planner_history.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

CONFIG = {
    "use_ai_planner": os.getenv("HIMORA_USE_AI_PLANNER", "false").lower() == "true",
    "ai_model": os.getenv("HIMORA_PLANNER_MODEL", "gpt-4.1-mini"),
    "chat_model": os.getenv("HIMORA_CHAT_MODEL", "gpt-4.1-mini"),
    "max_history": 30,
}


# =========================================================
# OPENAI CLIENT
# =========================================================
client = None

if OpenAI and OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception as error:
        print(f"[PLANNER] OpenAI client failed: {error}")


# =========================================================
# DATA MODELS
# =========================================================
@dataclass
class PlannerResult:
    type: str
    original_input: str
    cleaned_input: str
    task: Optional[Dict[str, Any]] = None
    response: str = ""
    confidence: float = 0.0
    reason: str = ""
    source: str = "deterministic"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =========================================================
# BASIC HELPERS
# =========================================================
def log(message: str):
    print(f"[PLANNER] {message}")


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
        path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as error:
        log(f"Could not write JSON: {error}")
        return False


def save_state(data: Dict[str, Any]):
    current = read_json(PLANNER_STATE_FILE, {})
    current.update(data)
    current["updated_at"] = time.time()
    write_json(PLANNER_STATE_FILE, current)


def save_history(item: Dict[str, Any]):
    history = read_json(PLANNER_HISTORY_FILE, [])
    if not isinstance(history, list):
        history = []

    history.append(item)
    history = history[-CONFIG["max_history"]:]
    write_json(PLANNER_HISTORY_FILE, history)


def clamp_percent(value: Any, default: int = 50) -> int:
    try:
        number = int(float(value))
    except Exception:
        number = default

    return max(0, min(100, number))


def task_single(action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "type": "single",
        "action": action,
        "params": params or {},
    }


def task_multi(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "type": "multi",
        "steps": steps,
    }


def step(action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "action": action,
        "params": params or {},
    }


def direct_response(text: str) -> Dict[str, Any]:
    return task_single("direct_response", {"response": text})


def natural_command_task(command: str) -> Dict[str, Any]:
    return task_single("natural_command", {"command": compact_spaces(command)})


# =========================================================
# NUMBER WORD NORMALIZATION
# =========================================================
NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "ten": 10,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fourty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
}


def replace_number_words(text: str) -> str:
    words = compact_spaces(text).split()
    output = []

    for word in words:
        low = normalize(word).strip(".,!?")
        if low in NUMBER_WORDS:
            output.append(str(NUMBER_WORDS[low]))
        else:
            output.append(word)

    return " ".join(output)


def basic_voice_cleanup(text: str) -> str:
    text = compact_spaces(text)
    text = replace_number_words(text)

    replacements = [
        (r"\bwife\b", "wifi"),
        (r"\bwi\s*fi\b", "wifi"),
        (r"\bwi-fi\b", "wifi"),
        (r"\bblue\s+tooth\b", "bluetooth"),
        (r"\byou\s+tube\b", "youtube"),
        (r"\bg\s+mail\b", "gmail"),
        (r"\bearth\s+quack\b", "earthquake"),
        (r"\bearthquack\b", "earthquake"),
        (r"\bwatsapp\b", "whatsapp"),
        (r"\bwotapp\b", "whatsapp"),
        (r"\bwhat\s+sap\b", "whatsapp"),
    ]

    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    filler_patterns = [
        r"^(himora|hey himora|hello himora|hi himora)\s+",
        r"^(please|can you|could you|would you|can you please|could you please)\s+",
        r"^(i want you to|i need you to|i want to)\s+",
    ]

    changed = True
    while changed:
        changed = False
        for pattern in filler_patterns:
            new_text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
            if new_text != text:
                text = new_text
                changed = True

    return compact_spaces(text)


def clean_command(text: str) -> str:
    text = compact_spaces(text)

    if canonicalize_command:
        try:
            return compact_spaces(canonicalize_command(text))
        except Exception:
            pass

    if normalize_voice_text:
        try:
            return compact_spaces(normalize_voice_text(text))
        except Exception:
            pass

    return basic_voice_cleanup(text)


# =========================================================
# INTENT DETECTION
# =========================================================
def is_whatsapp_like(text: str) -> bool:
    low = normalize(text)

    if any(word in low for word in ["whatsapp", "watsapp", "wotapp"]):
        return True

    if low.startswith(("msg ", "message ", "text ", "reply ", "call ", "voice call ", "video call ")):
        return True

    if low.startswith("ask "):
        return True

    if low.startswith(("write about ", "type about ", "reply about ")):
        return True

    if low in [
        "approve whatsapp bulk send",
        "cancel whatsapp bulk",
        "show pending whatsapp",
        "send whatsapp bulk",
    ]:
        return True

    return False


def is_gmail_like(text: str) -> bool:
    low = normalize(text)

    if any(word in low for word in ["gmail", "email", "mail"]):
        return True

    if low.startswith(("compose ", "draft ")):
        return True

    if low in ["send it", "yes send it", "discard email", "cancel email", "send email now"]:
        return True

    return False


def is_youtube_like(text: str) -> bool:
    low = normalize(text)

    if "youtube" in low:
        return True

    if low in ["pause the song", "resume the song", "change the song", "next song"]:
        return True

    if low.startswith(("play ", "pause ", "resume ", "next ", "change song")):
        if any(word in low for word in ["song", "music", "video"]):
            return True

    return False


def is_mac_like(text: str) -> bool:
    low = normalize(text)

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

    if low.startswith(starters):
        return True

    return False


def is_action_like(text: str) -> bool:
    return is_whatsapp_like(text) or is_gmail_like(text) or is_youtube_like(text) or is_mac_like(text)


# =========================================================
# SEQUENCE HANDLING
# =========================================================
def split_sequence(text: str) -> List[str]:
    text = compact_spaces(text)

    if not text:
        return []

    # Only split strong sequence words.
    # Do not split plain "and" because commands like
    # "open youtube and play shape of you" need to stay together.
    parts = re.split(
        r"\s+(?:and then|then|after that|next)\s+|;\s*",
        text,
        flags=re.IGNORECASE,
    )

    return [compact_spaces(part) for part in parts if compact_spaces(part)]


# =========================================================
# MAC STRUCTURED PLANS
# =========================================================
def plan_volume(text: str) -> Optional[Dict[str, Any]]:
    low = normalize(text)

    if low in ["mute", "mute volume", "mute sound"]:
        return task_single("mute", {})

    if low in ["unmute", "unmute volume", "unmute sound"]:
        return task_single("unmute", {})

    match = re.search(
        r"^(?:set\s+)?(?:volume|sound)\s+(?:to\s+)?(\d+)\s*(?:percent|%)?$",
        text,
        re.IGNORECASE,
    )
    if match:
        return task_single("set_volume", {"level": clamp_percent(match.group(1))})

    match = re.search(
        r"^(?:make|keep)\s+(?:the\s+)?(?:volume|sound)\s+(\d+)\s*(?:percent|%)?$",
        text,
        re.IGNORECASE,
    )
    if match:
        return task_single("set_volume", {"level": clamp_percent(match.group(1))})

    match = re.search(
        r"^(?:volume\s+up|increase\s+volume|turn\s+volume\s+up)(?:\s+by)?\s*(\d+)?\s*(?:percent|%)?$",
        text,
        re.IGNORECASE,
    )
    if match:
        return task_single("volume_up", {"percent": int(match.group(1) or 10)})

    match = re.search(
        r"^(?:volume\s+down|decrease\s+volume|reduce\s+volume|lower\s+volume|turn\s+volume\s+down)(?:\s+by)?\s*(\d+)?\s*(?:percent|%)?$",
        text,
        re.IGNORECASE,
    )
    if match:
        return task_single("volume_down", {"percent": int(match.group(1) or 10)})

    if low == "get volume":
        return task_single("get_volume", {})

    return None


def plan_brightness(text: str) -> Optional[Dict[str, Any]]:
    match = re.search(
        r"^(?:set\s+)?brightness\s+(?:to\s+)?(\d+)\s*(?:percent|%)?$",
        text,
        re.IGNORECASE,
    )

    if match:
        return task_single("set_brightness", {"level": clamp_percent(match.group(1), default=70)})

    return None


def plan_settings_network(text: str) -> Optional[Dict[str, Any]]:
    low = normalize(text)

    if low in ["wifi on", "turn wifi on", "enable wifi", "open wifi on"]:
        return task_single("wifi_on", {})

    if low in ["wifi off", "turn wifi off", "disable wifi", "close wifi", "turn off wifi"]:
        return task_single("wifi_off", {})

    if low in ["wifi status", "check wifi"]:
        return task_single("wifi_status", {})

    if low in ["bluetooth on", "turn bluetooth on", "enable bluetooth"]:
        return task_single("bluetooth_on", {})

    if low in ["bluetooth off", "turn bluetooth off", "disable bluetooth", "close bluetooth"]:
        return task_single("bluetooth_off", {})

    if low in ["bluetooth status", "check bluetooth"]:
        return task_single("bluetooth_status", {})

    if low in ["open wifi", "open wifi settings"]:
        return task_single("open_wifi_settings", {})

    if low in ["open bluetooth", "open bluetooth settings"]:
        return task_single("open_bluetooth_settings", {})

    match = re.search(
        r"^(?:open|search)\s+(?:settings|system settings)\s+(?:for\s+)?(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return task_single("open_settings", {"query": match.group(1).strip()})

    match = re.search(
        r"^open\s+(.+?)\s+settings$",
        text,
        re.IGNORECASE,
    )
    if match:
        return task_single("open_settings", {"query": match.group(1).strip()})

    if low in ["open settings", "open system settings", "system settings"]:
        return task_single("open_settings", {"query": ""})

    return None


def plan_files(text: str) -> Optional[Dict[str, Any]]:
    match = re.search(
        r"^(?:create|make)\s+(?:a\s+)?folder\s+(?:named\s+|called\s+)?(.+?)(?:\s+(?:in|on)\s+(desktop|downloads|documents|home|himora))?$",
        text,
        re.IGNORECASE,
    )
    if match:
        return task_single(
            "create_folder",
            {
                "name": match.group(1).strip(),
                "location": match.group(2) or "desktop",
            },
        )

    match = re.search(
        r"^(?:create|make)\s+(?:a\s+)?file\s+(?:named\s+|called\s+)?(.+?)(?:\s+(?:in|on)\s+(desktop|downloads|documents|home|himora))?$",
        text,
        re.IGNORECASE,
    )
    if match:
        return task_single(
            "create_file",
            {
                "name": match.group(1).strip(),
                "location": match.group(2) or "desktop",
                "content": "",
            },
        )

    match = re.search(r"^(?:find|search)\s+(?:the\s+)?file\s+(.+)$", text, re.IGNORECASE)
    if match:
        return task_single("finder_search", {"query": match.group(1).strip(), "location": "home"})

    match = re.search(r"^(?:find|search)\s+(?:the\s+)?(?:folder|directory)\s+(.+)$", text, re.IGNORECASE)
    if match:
        return task_single("finder_search", {"query": match.group(1).strip(), "location": "home"})

    match = re.search(r"^open\s+(?:the\s+)?file\s+(.+)$", text, re.IGNORECASE)
    if match:
        return task_single("open_best_match", {"query": match.group(1).strip(), "kind": "file"})

    match = re.search(r"^open\s+(?:the\s+)?(?:folder|directory)\s+(.+)$", text, re.IGNORECASE)
    if match:
        return task_single("open_best_match", {"query": match.group(1).strip(), "kind": "folder"})

    match = re.search(r"^search\s+finder\s+(?:for\s+)?(.+)$", text, re.IGNORECASE)
    if match:
        return task_single("finder_search", {"query": match.group(1).strip(), "location": "home"})

    return None


def plan_keyboard_mouse(text: str) -> Optional[Dict[str, Any]]:
    low = normalize(text)

    if low == "screenshot":
        return task_single("screenshot", {})

    if low in ["front app", "current app"]:
        return task_single("frontmost_app", {})

    if low == "bounds":
        return task_single("get_front_window_bounds", {})

    match = re.search(r"^click\s+(-?\d+)\s+(-?\d+)$", text, re.IGNORECASE)
    if match:
        return task_single("click", {"x": int(match.group(1)), "y": int(match.group(2))})

    match = re.search(r"^scroll\s+down(?:\s+(\d+))?$", text, re.IGNORECASE)
    if match:
        return task_single("scroll_down", {"amount": int(match.group(1) or 5)})

    match = re.search(r"^scroll\s+up(?:\s+(\d+))?$", text, re.IGNORECASE)
    if match:
        return task_single("scroll_up", {"amount": int(match.group(1) or 5)})

    match = re.search(r"^press\s+(.+)$", text, re.IGNORECASE)
    if match:
        return task_single("press", {"key": match.group(1).strip()})

    match = re.search(r"^hotkey\s+(.+)$", text, re.IGNORECASE)
    if match:
        keys = [part.strip() for part in re.split(r"\+|\s+", match.group(1).strip()) if part.strip()]
        return task_single("hotkey", {"keys": keys})

    match = re.search(r"^type\s+(.+)$", text, re.IGNORECASE)
    if match:
        return task_single("type_text", {"text": match.group(1).strip()})

    match = re.search(r"^paste\s+(.+)$", text, re.IGNORECASE)
    if match:
        return task_single("paste_text", {"text": match.group(1).strip()})

    return None


def plan_apps_web(text: str) -> Optional[Dict[str, Any]]:
    low = normalize(text)

    match = re.search(r"^(?:launch|start|run)\s+(.+)$", text, re.IGNORECASE)
    if match:
        return task_single("open_app", {"app": match.group(1).strip()})

    match = re.search(r"^(?:close|quit|exit)\s+(.+)$", text, re.IGNORECASE)
    if match:
        return task_single("close_app", {"app": match.group(1).strip()})

    match = re.search(r"^activate\s+(.+)$", text, re.IGNORECASE)
    if match:
        return task_single("activate_app", {"app": match.group(1).strip()})

    match = re.search(r"^spotlight\s+(.+)$", text, re.IGNORECASE)
    if match:
        return task_single("spotlight_open", {"query": match.group(1).strip()})

    match = re.search(r"^search\s+(.+)$", text, re.IGNORECASE)
    if match:
        return task_single("google_search", {"query": match.group(1).strip()})

    if low.startswith("open "):
        target = text[5:].strip()

        if re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/.*)?$", target):
            return task_single("open_url", {"url": target})

        if target.startswith(("http://", "https://")):
            return task_single("open_url", {"url": target})

        return task_single("open_app", {"app": target})

    return None


def plan_mac_structured(text: str) -> Optional[Dict[str, Any]]:
    planners = [
        plan_volume,
        plan_brightness,
        plan_settings_network,
        plan_files,
        plan_keyboard_mouse,
        plan_apps_web,
    ]

    for planner in planners:
        result = planner(text)
        if result:
            return result

    return None


# =========================================================
# MAIN DETERMINISTIC PLANNER
# =========================================================
def deterministic_plan_one(original: str, cleaned: str) -> PlannerResult:
    low = normalize(cleaned)

    if not cleaned:
        return PlannerResult(
            type="direct",
            original_input=original,
            cleaned_input=cleaned,
            response="I did not hear anything clearly.",
            confidence=0.95,
            reason="empty",
        )

    if low in ["help", "commands", "what can you do"]:
        return PlannerResult(
            type="direct",
            original_input=original,
            cleaned_input=cleaned,
            response=help_text(),
            confidence=0.99,
            reason="help",
        )

    # Approval phrases should go through executor natural routing.
    if low in [
        "send it",
        "yes send it",
        "send email now",
        "discard email",
        "cancel email",
        "approve whatsapp bulk send",
        "cancel whatsapp bulk",
        "show pending whatsapp",
    ]:
        return PlannerResult(
            type="action",
            original_input=original,
            cleaned_input=cleaned,
            task=natural_command_task(cleaned),
            confidence=0.98,
            reason="approval command",
        )

    # Dedicated agents
    if is_whatsapp_like(cleaned):
        return PlannerResult(
            type="action",
            original_input=original,
            cleaned_input=cleaned,
            task=task_single("whatsapp_from_command", {"command": cleaned}),
            confidence=0.94,
            reason="whatsapp command",
        )

    if is_gmail_like(cleaned):
        return PlannerResult(
            type="action",
            original_input=original,
            cleaned_input=cleaned,
            task=task_single("gmail_from_command", {"command": cleaned}),
            confidence=0.94,
            reason="gmail command",
        )

    if is_youtube_like(cleaned):
        return PlannerResult(
            type="action",
            original_input=original,
            cleaned_input=cleaned,
            task=task_single("youtube_from_command", {"command": cleaned}),
            confidence=0.94,
            reason="youtube command",
        )

    # Mac actions
    mac_task = plan_mac_structured(cleaned)
    if mac_task:
        return PlannerResult(
            type="action",
            original_input=original,
            cleaned_input=cleaned,
            task=mac_task,
            confidence=0.92,
            reason="structured mac command",
        )

    # If it still looks like action, let executor natural parser try.
    if is_action_like(cleaned):
        return PlannerResult(
            type="action",
            original_input=original,
            cleaned_input=cleaned,
            task=natural_command_task(cleaned),
            confidence=0.75,
            reason="action-like fallback",
        )

    return PlannerResult(
        type="chat",
        original_input=original,
        cleaned_input=cleaned,
        task=None,
        confidence=0.70,
        reason="chat",
    )


def deterministic_plan(user_input: str) -> PlannerResult:
    original = compact_spaces(user_input)

    if route_input:
        try:
            route = route_input(original)
            cleaned = compact_spaces(route.get("cleaned_input") or route.get("command") or original)
        except Exception:
            cleaned = clean_command(original)
    else:
        cleaned = clean_command(original)

    parts = split_sequence(cleaned)

    if len(parts) > 1:
        steps = []
        reasons = []

        for part in parts:
            partial = deterministic_plan_one(part, part)

            if partial.type == "action" and partial.task:
                task = partial.task

                if task.get("type") == "single":
                    steps.append(
                        {
                            "action": task.get("action"),
                            "params": task.get("params", {}),
                        }
                    )

                elif task.get("type") == "multi":
                    steps.extend(task.get("steps", []))

                reasons.append(partial.reason)

        if steps:
            return PlannerResult(
                type="action",
                original_input=original,
                cleaned_input=cleaned,
                task=task_multi(steps),
                confidence=0.88,
                reason="sequence: " + ", ".join(reasons),
            )

    return deterministic_plan_one(original, cleaned)


# =========================================================
# OPTIONAL AI PLANNER
# =========================================================
def ai_plan(user_input: str, deterministic: PlannerResult) -> Optional[PlannerResult]:
    if not CONFIG["use_ai_planner"]:
        return None

    if client is None:
        return None

    # Do not use AI planner when deterministic is already confident.
    if deterministic.type == "action" and deterministic.confidence >= 0.90:
        return None

    system_prompt = """
You are Himora's planner.

Convert the user's command into a JSON task for executor.py.

Allowed output types:
1. action
2. chat
3. direct

Allowed actions:
- natural_command
- whatsapp_from_command
- youtube_from_command
- gmail_from_command
- open_app
- close_app
- open_url
- google_search
- open_settings
- open_wifi_settings
- open_bluetooth_settings
- wifi_on
- wifi_off
- bluetooth_on
- bluetooth_off
- set_volume
- volume_up
- volume_down
- set_brightness
- create_folder
- create_file
- finder_search
- open_best_match
- spotlight_open
- click
- scroll_down
- scroll_up
- press
- hotkey
- type_text
- paste_text
- screenshot

Return ONLY valid JSON in this format:
{
  "type": "action" | "chat" | "direct",
  "cleaned_input": "...",
  "task": {
    "type": "single",
    "action": "...",
    "params": {}
  },
  "response": "",
  "confidence": 0.0,
  "reason": "..."
}

Rules:
- WhatsApp commands should usually use whatsapp_from_command with the cleaned command.
- YouTube commands should usually use youtube_from_command.
- Gmail/email commands should usually use gmail_from_command.
- Mac system commands should use structured actions when obvious.
- Do not invent dangerous behavior.
- If unsure, use natural_command.
"""

    user_prompt = f"""
Original input:
{user_input}

Deterministic cleaned input:
{deterministic.cleaned_input}

Deterministic result:
{json.dumps(deterministic.to_dict(), ensure_ascii=False, indent=2)}

Create the best planner JSON.
"""

    try:
        response = client.chat.completions.create(
            model=CONFIG["ai_model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
        )

        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)

        result_type = data.get("type", "chat")
        cleaned = compact_spaces(data.get("cleaned_input") or deterministic.cleaned_input or user_input)
        task = data.get("task")
        response_text = clean_text(data.get("response", ""))
        confidence = float(data.get("confidence", 0.60))
        reason = clean_text(data.get("reason", "ai planner"))

        if result_type == "action" and isinstance(task, dict):
            return PlannerResult(
                type="action",
                original_input=user_input,
                cleaned_input=cleaned,
                task=task,
                response="",
                confidence=confidence,
                reason=reason,
                source="ai",
            )

        if result_type == "direct":
            return PlannerResult(
                type="direct",
                original_input=user_input,
                cleaned_input=cleaned,
                response=response_text,
                confidence=confidence,
                reason=reason,
                source="ai",
            )

        return PlannerResult(
            type="chat",
            original_input=user_input,
            cleaned_input=cleaned,
            confidence=confidence,
            reason=reason,
            source="ai",
        )

    except Exception as error:
        log(f"AI planner failed: {error}")
        return None


# =========================================================
# PUBLIC PLANNER API
# =========================================================
def plan(user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    deterministic = deterministic_plan(user_input)
    improved = ai_plan(user_input, deterministic)
    final = improved or deterministic

    save_state(
        {
            "last_input": user_input,
            "last_cleaned_input": final.cleaned_input,
            "last_type": final.type,
            "last_reason": final.reason,
            "last_source": final.source,
        }
    )

    save_history(final.to_dict())

    return final.to_dict()


def create_plan(user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return plan(user_input, context=context)


def plan_task(user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return plan(user_input, context=context)


def parse_and_plan(user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return plan(user_input, context=context)


def expand_task(user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Compatibility function.

    Older main.py versions expected planner.expand_task()
    to return only the executable task.
    """
    result = plan(user_input, context=context)

    if result.get("type") == "action" and result.get("task"):
        return result["task"]

    if result.get("type") == "direct":
        return direct_response(result.get("response", ""))

    return natural_command_task(result.get("cleaned_input") or user_input)


def is_action_request(user_input: str) -> bool:
    result = plan(user_input)
    return result.get("type") == "action"


# =========================================================
# CHAT / FOLLOW-UP COMPATIBILITY
# =========================================================
def follow_up(user_input: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Compatibility chat function.

    If main.py still calls planner.follow_up(),
    this gives a normal AI response.
    """
    user_input = compact_spaces(user_input)

    if not user_input:
        return "I did not hear anything clearly."

    if client is None:
        return (
            "I can answer that, but the OpenAI client is not available. "
            "Please check your OPENAI_API_KEY in the .env file."
        )

    system_prompt = """
You are Himora, Aayu's advanced Mac desktop AI assistant.

Answer normally when the user is chatting.
Be practical, direct, and helpful.
If the user asks for a computer action, tell them it should be routed to executor.py.
"""

    try:
        response = client.chat.completions.create(
            model=CONFIG["chat_model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            temperature=0.55,
        )

        return response.choices[0].message.content.strip()

    except Exception as error:
        return f"I could not generate a follow-up response: {error}"


# =========================================================
# HELP
# =========================================================
def help_text() -> str:
    return """
Planner examples:

Mac:
- volume 40
- volume up 20
- volume down 10
- open bluetooth settings
- wifi off
- bluetooth on
- create folder Himora Test in desktop
- find file main.py
- open folder Himora
- open calculator
- spotlight activity monitor

WhatsApp:
- msg dad hello
- send hello to dad on whatsapp
- message dad about earthquake
- ask dad how are you after earthquake
- call dad

YouTube:
- open youtube and play shape of you
- pause the song
- resume the song

Gmail:
- open gmail
- compose gmail to someone@gmail.com about cyber fraud
- send it
""".strip()


# =========================================================
# DIRECT TEST
# =========================================================
if __name__ == "__main__":
    print("=" * 60)
    print("HIMORA PLANNER TEST v3")
    print("=" * 60)
    print("Try:")
    print("- himora can you please turn the wife off")
    print("- make volume forty percent")
    print("- open blue tooth setting")
    print("- create folder Test Project in desktop")
    print("- find file main.py")
    print("- open folder Himora")
    print("- send hello to dad on whatsapp")
    print("- message dad about earth quack")
    print("- ask dad how are you after earth quack")
    print("- play shape of you in you tube")
    print("- compose gmail to test@gmail.com about cyber fraud")
    print("- open calculator then volume down 10")
    print("- exit")
    print("=" * 60)

    while True:
        try:
            command = input("\nplanner command: ").strip()

            if command.lower() in ["exit", "quit"]:
                break

            result = plan(command)
            print(json.dumps(result, indent=2, ensure_ascii=False))

        except KeyboardInterrupt:
            print("\nStopped.")
            break

        except Exception:
            traceback.print_exc()