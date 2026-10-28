"""
Himora whatsapp_agent.py - Final Stable WhatsApp Controller
-----------------------------------------------------------

Main flow requested by Aayu:

1. Press Command + Space
2. Spotlight opens
3. Type ONLY the person's name, for example: dad
4. Press Enter
5. WhatsApp chat opens
6. Click message box
7. Paste message
8. Press Enter to send

Examples:
- msg dad hello
- message dad hello
- send hello to dad on whatsapp
- ask dad how are you after earthquake
- write to dad about earthquake
- reply hello
- open whatsapp
- dad means +97798XXXXXXXX
- show whatsapp contacts

Required:
python -m pip install pyautogui pyperclip python-dotenv openai pillow pytesseract

macOS permissions:
System Settings -> Privacy & Security:
- Accessibility
- Input Monitoring
- Automation
- Screen Recording
"""

import os
import re
import json
import time
import difflib
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


try:
    import pyautogui
    pyautogui.FAILSAFE = True
except Exception:
    pyautogui = None


try:
    import pyperclip
except Exception:
    pyperclip = None


try:
    from openai import OpenAI
except Exception:
    OpenAI = None


try:
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter
except Exception:
    Image = None
    ImageOps = None
    ImageEnhance = None
    ImageFilter = None


try:
    import pytesseract

    if Path("/opt/homebrew/bin/tesseract").exists():
        pytesseract.pytesseract.tesseract_cmd = "/opt/homebrew/bin/tesseract"
    elif Path("/usr/local/bin/tesseract").exists():
        pytesseract.pytesseract.tesseract_cmd = "/usr/local/bin/tesseract"
except Exception:
    pytesseract = None


# =========================================================
# PATHS / CONFIG
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory_data"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

CONTACTS_FILE = MEMORY_DIR / "whatsapp_contacts.json"
PENDING_FILE = MEMORY_DIR / "whatsapp_pending.json"
STATE_FILE = MEMORY_DIR / "whatsapp_agent_state.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

CONFIG = {
    "model": os.getenv("HIMORA_WHATSAPP_MODEL", "gpt-4o-mini"),

    # Main behavior
    "send_by_default": os.getenv("HIMORA_WHATSAPP_SEND_BY_DEFAULT", "true").lower() == "true",

    # Timing
    "spotlight_open_wait": float(os.getenv("HIMORA_SPOTLIGHT_OPEN_WAIT", "0.55")),
    "spotlight_result_wait": float(os.getenv("HIMORA_SPOTLIGHT_RESULT_WAIT", "0.75")),
    "chat_open_wait": float(os.getenv("HIMORA_WHATSAPP_CHAT_OPEN_WAIT", "1.4")),
    "app_open_wait": float(os.getenv("HIMORA_WHATSAPP_APP_OPEN_WAIT", "1.2")),
    "paste_wait": float(os.getenv("HIMORA_WHATSAPP_PASTE_WAIT", "0.20")),

    # Important: Spotlight searches ONLY target name.
    "spotlight_target_only": True,

    # Fallback if Spotlight does not open the chat.
    "use_whatsapp_search_fallback": True,

    # Debug logs
    "debug": os.getenv("HIMORA_WHATSAPP_DEBUG", "true").lower() == "true",

    # OCR
    "ocr_min_confidence": int(os.getenv("HIMORA_WHATSAPP_OCR_CONF", "20")),
}

client = None

if OpenAI and OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception as error:
        print(f"[WHATSAPP] OpenAI client failed: {error}")


# =========================================================
# BASIC HELPERS
# =========================================================

def log(message: str):
    if CONFIG["debug"]:
        print(f"[WHATSAPP] {message}")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def compact_spaces(text: Any) -> str:
    return re.sub(r"\s+", " ", clean_text(text)).strip()


def normalize(text: Any) -> str:
    return compact_spaces(text).lower()


def read_json(path: Path, default: Any):
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data
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
        log(f"JSON write failed: {error}")
        return False


def ensure_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def save_state(data: Dict[str, Any]):
    current = read_json(STATE_FILE, {})

    if not isinstance(current, dict):
        current = {}

    current.update(data)
    current["updated_at"] = time.time()

    write_json(STATE_FILE, current)


def sleep(seconds: float):
    time.sleep(seconds)


def run_shell(command: List[str], timeout: int = 8) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def run_osascript(script: str, timeout: int = 8) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def safe_hotkey(*keys: str):
    if pyautogui:
        pyautogui.hotkey(*keys)


def safe_press(key: str, presses: int = 1, interval: float = 0.05):
    if pyautogui:
        pyautogui.press(key, presses=presses, interval=interval)


def set_clipboard(text: str) -> bool:
    text = clean_text(text)

    if pyperclip:
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            pass

    try:
        process = subprocess.Popen(
            ["pbcopy"],
            stdin=subprocess.PIPE,
            text=True,
        )
        process.communicate(text, timeout=3)
        return True
    except Exception:
        return False


def paste_text(text: str) -> bool:
    text = clean_text(text)

    if not text or not pyautogui:
        return False

    if set_clipboard(text):
        sleep(0.06)
        safe_hotkey("command", "v")
        return True

    try:
        pyautogui.write(text, interval=0.01)
        return True
    except Exception:
        return False


def phone_digits(text: str) -> str:
    return re.sub(r"\D+", "", clean_text(text))


def looks_like_phone(text: str) -> bool:
    digits = phone_digits(text)
    return len(digits) >= 8


def clean_phone_for_url(text: str) -> str:
    digits = phone_digits(text)

    if digits.startswith("00"):
        digits = digits[2:]

    return digits


# =========================================================
# APP / WINDOW CONTROL
# =========================================================

def frontmost_app_name() -> str:
    script = """
    tell application "System Events"
        try
            set frontApp to name of first application process whose frontmost is true
            return frontApp
        on error
            return ""
        end try
    end tell
    """
    return clean_text(run_osascript(script))


def is_whatsapp_active() -> bool:
    return "whatsapp" in normalize(frontmost_app_name())


def open_whatsapp_app() -> bool:
    run_shell(["open", "-a", "WhatsApp"])
    sleep(CONFIG["app_open_wait"])

    if is_whatsapp_active():
        return True

    run_shell(["open", "-a", "WhatsApp Desktop"])
    sleep(CONFIG["app_open_wait"])

    return is_whatsapp_active()


def open_whatsapp() -> str:
    if open_whatsapp_app():
        return "WhatsApp opened."
    return "I tried to open WhatsApp, but it did not become active."


def get_whatsapp_window_bounds() -> Optional[Tuple[int, int, int, int]]:
    script = """
    tell application "System Events"
        try
            tell process "WhatsApp"
                set frontmost to true
                delay 0.1
                set p to position of front window
                set s to size of front window
                return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)
            end tell
        on error
            return ""
        end try
    end tell
    """

    output = run_osascript(script)

    try:
        parts = [int(float(x.strip())) for x in output.split(",")]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    except Exception:
        return None

    return None


def click_message_box() -> bool:
    """
    Clicks near the bottom input field of WhatsApp.
    This is more reliable than trying to OCR the input box.
    """

    if not pyautogui:
        return False

    bounds = get_whatsapp_window_bounds()

    if bounds:
        x, y, w, h = bounds

        points = [
            (x + int(w * 0.62), y + h - 54),
            (x + int(w * 0.58), y + h - 68),
            (x + int(w * 0.70), y + h - 58),
            (x + int(w * 0.50), y + h - 56),
        ]

        for px, py in points:
            try:
                pyautogui.click(px, py)
                sleep(0.20)
                return True
            except Exception:
                pass

    try:
        screen_w, screen_h = pyautogui.size()
        pyautogui.click(int(screen_w * 0.65), int(screen_h * 0.90))
        sleep(0.20)
        return True
    except Exception:
        return False


# =========================================================
# CONTACT MEMORY
# =========================================================

def contact_key(name: str) -> str:
    key = normalize(name)
    key = re.sub(r"[^a-z0-9_]+", "_", key)
    key = re.sub(r"_+", "_", key).strip("_")
    return key


def load_contacts() -> Dict[str, Any]:
    data = read_json(CONTACTS_FILE, {})

    if isinstance(data, dict):
        return data

    return {}


def save_contacts(data: Dict[str, Any]):
    write_json(CONTACTS_FILE, data)


def save_contact_alias(name: str, value: str) -> str:
    name = compact_spaces(name)
    value = compact_spaces(value)

    if not name or not value:
        return "I need both contact name and value."

    contacts = load_contacts()
    contacts[contact_key(name)] = {
        "name": name,
        "value": value,
        "updated_at": time.time(),
    }

    save_contacts(contacts)
    return f"Saved WhatsApp contact alias: {name}."


def resolve_contact(target: str) -> Dict[str, str]:
    """
    Handles both new and old contact formats safely.

    New format:
    {
        "dad": {"name": "dad", "value": "+97798..."}
    }

    Old/broken format:
    {
        "dad": "+97798..."
    }
    """

    target = compact_spaces(target)
    contacts = load_contacts()
    key = contact_key(target)

    item = contacts.get(key)

    if isinstance(item, dict):
        return {
            "name": clean_text(item.get("name", target)) or target,
            "value": clean_text(item.get("value", target)) or target,
            "source": "memory_dict",
        }

    if isinstance(item, str):
        return {
            "name": target,
            "value": item,
            "source": "memory_string",
        }

    return {
        "name": target,
        "value": target,
        "source": "raw",
    }


def show_contacts() -> str:
    contacts = load_contacts()

    if not contacts:
        return "No WhatsApp contact aliases saved yet."

    lines = []

    for key, item in contacts.items():
        if isinstance(item, dict):
            name = item.get("name", key)
            value = item.get("value", "")
        else:
            name = key
            value = str(item)

        lines.append(f"- {name}: {value}")

    return "Saved WhatsApp contacts:\n" + "\n".join(lines)


# =========================================================
# OCR OPTIONAL FOR CALL BUTTONS
# =========================================================

def ocr_available() -> bool:
    return bool(pyautogui and Image and ImageOps and pytesseract)


def preprocess_for_ocr(img):
    if img is None or ImageOps is None:
        return img

    try:
        processed = img.convert("L")
        processed = ImageOps.autocontrast(processed)

        if ImageEnhance:
            processed = ImageEnhance.Contrast(processed).enhance(1.4)

        if ImageFilter:
            processed = processed.filter(ImageFilter.SHARPEN)

        processed = processed.resize((processed.width * 2, processed.height * 2))
        return processed
    except Exception:
        return img


def ocr_lines() -> List[Dict[str, Any]]:
    if not ocr_available():
        return []

    try:
        img = pyautogui.screenshot()
    except Exception:
        return []

    processed = preprocess_for_ocr(img)
    scale_x = processed.width / max(1, img.width)
    scale_y = processed.height / max(1, img.height)

    try:
        data = pytesseract.image_to_data(
            processed,
            output_type=pytesseract.Output.DICT,
            config="--oem 3 --psm 6",
        )
    except Exception:
        return []

    grouped: Dict[Tuple[int, int, int], List[int]] = {}
    count = len(data.get("text", []))

    for i in range(count):
        text = clean_text(data["text"][i])

        if not text:
            continue

        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1

        if conf < CONFIG["ocr_min_confidence"]:
            continue

        key = (
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
        )

        grouped.setdefault(key, []).append(i)

    lines = []

    for indexes in grouped.values():
        words = []
        xs = []
        ys = []
        rights = []
        bottoms = []

        for i in indexes:
            word = clean_text(data["text"][i])

            if not word:
                continue

            x = int(data["left"][i]) / scale_x
            y = int(data["top"][i]) / scale_y
            w = int(data["width"][i]) / scale_x
            h = int(data["height"][i]) / scale_y

            words.append(word)
            xs.append(x)
            ys.append(y)
            rights.append(x + w)
            bottoms.append(y + h)

        if not words:
            continue

        line_text = compact_spaces(" ".join(words))

        if not line_text:
            continue

        x1 = int(min(xs))
        y1 = int(min(ys))
        x2 = int(max(rights))
        y2 = int(max(bottoms))

        lines.append(
            {
                "text": line_text,
                "x": x1,
                "y": y1,
                "w": max(1, x2 - x1),
                "h": max(1, y2 - y1),
            }
        )

    lines.sort(key=lambda item: (item["y"], item["x"]))
    return lines


def score_text_match(text: str, query: str) -> float:
    text_low = normalize(text)
    query_low = normalize(query)

    if not text_low or not query_low:
        return 0.0

    if text_low == query_low:
        return 1.0

    if query_low in text_low:
        return 0.95

    return difflib.SequenceMatcher(None, text_low, query_low).ratio()


def click_ocr_text(query: str) -> bool:
    if not pyautogui:
        return False

    lines = ocr_lines()

    best = None
    best_score = 0.0

    for line in lines:
        score = score_text_match(line.get("text", ""), query)

        if score > best_score:
            best_score = score
            best = line

    if not best or best_score < 0.55:
        return False

    try:
        x = best["x"] + best["w"] // 2
        y = best["y"] + best["h"] // 2
        pyautogui.click(x, y)
        sleep(0.35)
        return True
    except Exception:
        return False


# =========================================================
# MESSAGE GENERATION
# =========================================================

def generate_message(target: str, instruction: str) -> str:
    target = compact_spaces(target)
    instruction = compact_spaces(instruction)

    if not instruction:
        return ""

    low = normalize(instruction)

    # Keep exact short messages exact.
    if not low.startswith("about "):
        return instruction[0].upper() + instruction[1:] if instruction else instruction

    if client:
        prompt = f"""
Write a short WhatsApp message.

Recipient/name:
{target}

Instruction/topic:
{instruction}

Rules:
- Keep it natural.
- Keep it short.
- No subject line.
- No email style.
- Return only the message text.
"""

        try:
            response = client.chat.completions.create(
                model=CONFIG["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.45,
                max_tokens=120,
            )

            return response.choices[0].message.content.strip()
        except Exception:
            pass

    topic = instruction.replace("about ", "", 1).strip()

    if "earthquake" in low:
        return "I just wanted to check on you after the earthquake. Are you safe?"

    return f"I wanted to talk to you about {topic}."


# =========================================================
# CHAT OPENING METHODS
# =========================================================

def open_chat_via_spotlight(target_name: str) -> bool:
    """
    Main requested method.

    It types ONLY the target name in Spotlight.
    Example:
        dad

    It does NOT type:
        WhatsApp dad
    """

    if not pyautogui:
        return False

    target_name = compact_spaces(target_name)

    if not target_name:
        return False

    try:
        log(f"Spotlight search target only: {target_name}")

        safe_hotkey("command", "space")
        sleep(CONFIG["spotlight_open_wait"])

        # Clear existing Spotlight text just in case.
        safe_hotkey("command", "a")
        sleep(0.05)

        paste_text(target_name)
        sleep(CONFIG["spotlight_result_wait"])

        safe_press("enter")
        sleep(CONFIG["chat_open_wait"])

        # If Spotlight opened the chat/app correctly, WhatsApp should be active.
        if is_whatsapp_active():
            return True

        return False

    except Exception as error:
        log(f"Spotlight method failed: {error}")
        return False


def open_chat_via_whatsapp_search(target_name: str) -> bool:
    """
    Fallback inside WhatsApp.

    This also types ONLY the target name.
    It does not type 'WhatsApp dad'.
    """

    if not pyautogui:
        return False

    target_name = compact_spaces(target_name)

    if not target_name:
        return False

    if not open_whatsapp_app():
        return False

    try:
        log(f"WhatsApp search target only: {target_name}")

        # Command + N usually opens new chat/search in WhatsApp desktop.
        safe_hotkey("command", "n")
        sleep(0.65)

        paste_text(target_name)
        sleep(0.85)

        safe_press("enter")
        sleep(CONFIG["chat_open_wait"])

        return is_whatsapp_active()

    except Exception as error:
        log(f"WhatsApp search fallback failed: {error}")
        return False


def open_chat_via_phone_url(phone: str) -> bool:
    phone = clean_phone_for_url(phone)

    if not phone:
        return False

    try:
        run_shell(["open", f"whatsapp://send?phone={phone}"])
        sleep(CONFIG["chat_open_wait"])
        return is_whatsapp_active()
    except Exception:
        return False


def open_chat(target: str) -> bool:
    """
    Opens chat.

    If target resolves to phone number:
    - Try WhatsApp phone URL first.

    Otherwise:
    - Spotlight with target name only.
    - Fallback WhatsApp search with target name only.
    """

    target = compact_spaces(target)
    resolved = resolve_contact(target)

    target_name = resolved.get("name", target)
    target_value = resolved.get("value", target)

    save_state(
        {
            "last_open_target": target,
            "last_resolved_name": target_name,
            "last_resolved_value": target_value,
            "last_resolved_source": resolved.get("source", "unknown"),
        }
    )

    # If saved value is phone, use URL.
    if looks_like_phone(target_value):
        if open_chat_via_phone_url(target_value):
            return True

    # Main requested method: Spotlight with ONLY original target name.
    if open_chat_via_spotlight(target_name):
        return True

    # Fallback: WhatsApp search with ONLY target name.
    if CONFIG["use_whatsapp_search_fallback"]:
        if open_chat_via_whatsapp_search(target_name):
            return True

    return False


# =========================================================
# SEND / REPLY
# =========================================================

def send_message_to_current_chat(message: str, send: bool = True) -> str:
    message = clean_text(message)

    if not message:
        return "Message is empty."

    if not open_whatsapp_app():
        return "WhatsApp is not active."

    if not click_message_box():
        return "I could not click the message box."

    if not paste_text(message):
        return "I could not type the message."

    sleep(CONFIG["paste_wait"])

    if send:
        safe_press("enter")
        sleep(0.25)
        return "Message sent."

    return "Message drafted."


def send_message_to_target(target: str, message: str, send: bool = True) -> str:
    target = compact_spaces(target)
    message = clean_text(message)

    if not target:
        return "Who should I message?"

    if not message:
        return "What message should I send?"

    opened = open_chat(target)

    if not opened:
        return (
            f"I could not open WhatsApp chat for '{target}'. "
            f"Make sure the chat appears in Spotlight when you search '{target}', "
            f"or save the number using: {target} means +97798XXXXXXXX"
        )

    sleep(0.35)

    result = send_message_to_current_chat(message, send=send)

    save_state(
        {
            "last_send_target": target,
            "last_send_message": message,
            "last_send_result": result,
        }
    )

    if result == "Message sent.":
        return f"Sent WhatsApp message to {target}."

    return result


def reply_current_chat(message: str, send: bool = True) -> str:
    message = clean_text(message)

    if not message:
        return "What should I reply?"

    return send_message_to_current_chat(message, send=send)


# =========================================================
# PENDING APPROVAL
# =========================================================

def save_pending(target: str, message: str):
    pending = {
        "type": "whatsapp",
        "target": compact_spaces(target),
        "message": clean_text(message),
        "created_at": time.time(),
    }

    write_json(PENDING_FILE, pending)


def load_pending() -> Dict[str, Any]:
    data = read_json(PENDING_FILE, {})

    if isinstance(data, dict):
        return data

    return {}


def clear_pending():
    try:
        if PENDING_FILE.exists():
            PENDING_FILE.unlink()
    except Exception:
        pass


def pending_summary() -> str:
    pending = load_pending()

    if not pending:
        return "No pending WhatsApp message."

    return (
        "Pending WhatsApp message:\n"
        f"To: {pending.get('target', '')}\n"
        f"Message: {pending.get('message', '')}"
    )


def send_pending() -> str:
    pending = load_pending()

    if not pending:
        return "No pending WhatsApp message."

    target = pending.get("target", "")
    message = pending.get("message", "")

    result = send_message_to_target(target, message, send=True)

    if "Sent WhatsApp message" in result or result == "Message sent.":
        clear_pending()

    return result


def handle_whatsapp_approval_command(text: str) -> Optional[str]:
    low = normalize(text)

    if low in {
        "send pending whatsapp",
        "send whatsapp pending",
        "approve whatsapp",
        "approve whatsapp message",
        "yes send whatsapp",
        "yes send it",
        "send it",
    }:
        return send_pending()

    if low in {
        "cancel whatsapp",
        "cancel whatsapp message",
        "discard whatsapp",
        "discard whatsapp message",
        "delete pending whatsapp",
        "cancel pending whatsapp",
    }:
        clear_pending()
        return "Cancelled pending WhatsApp message."

    if low in {
        "show pending whatsapp",
        "pending whatsapp",
        "whatsapp pending",
    }:
        return pending_summary()

    return None


# =========================================================
# COMMAND PARSER
# =========================================================

def strip_whatsapp_words(text: str) -> str:
    text = compact_spaces(text)
    text = re.sub(r"\bon\s+whats\s*app\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bon\s+whatsapp\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bwhats\s*app\b", "whatsapp", text, flags=re.IGNORECASE)
    return compact_spaces(text)


def parse_save_contact_command(command: str) -> Optional[Tuple[str, str]]:
    raw = compact_spaces(command)

    patterns = [
        r"^(.+?)\s+means\s+(.+)$",
        r"^remember\s+(.+?)\s+as\s+(.+)$",
        r"^save\s+(.+?)\s+as\s+(.+)$",
        r"^save\s+contact\s+(.+?)\s+as\s+(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)

        if match:
            name = match.group(1).strip()
            value = match.group(2).strip()

            if name and value:
                return name, value

    return None


def parse_message_command(command: str) -> Dict[str, Any]:
    original = compact_spaces(command)
    command = strip_whatsapp_words(original)
    low = normalize(command)

    save_contact = parse_save_contact_command(command)

    if save_contact:
        name, value = save_contact
        return {
            "action": "save_contact",
            "name": name,
            "value": value,
        }

    if low in ["open whatsapp", "whatsapp", "open whats app"]:
        return {"action": "open"}

    if low in ["show whatsapp contacts", "show contacts", "whatsapp contacts"]:
        return {"action": "show_contacts"}

    if low in ["pending whatsapp", "show pending whatsapp", "whatsapp pending"]:
        return {"action": "pending"}

    if low in ["send pending whatsapp", "approve whatsapp", "yes send whatsapp", "send it"]:
        return {"action": "send_pending"}

    if low in ["cancel whatsapp", "cancel pending whatsapp", "discard whatsapp"]:
        return {"action": "cancel_pending"}

    # reply hello
    match = re.search(r"^reply\s+(.+)$", command, re.IGNORECASE)
    if match:
        return {
            "action": "reply",
            "message": match.group(1).strip(),
            "send": True,
        }

    draft = False

    if low.startswith("draft "):
        draft = True
        command = command[6:].strip()
        low = normalize(command)

    # send hello to dad
    match = re.search(r"^send\s+(.+?)\s+to\s+(.+)$", command, re.IGNORECASE)
    if match:
        message = match.group(1).strip()
        target = match.group(2).strip()

        return {
            "action": "send",
            "target": target,
            "message": message,
            "send": not draft,
        }

    # ask dad how are you after earthquake
    match = re.search(r"^ask\s+(.+?)\s+(.+)$", command, re.IGNORECASE)
    if match:
        target = match.group(1).strip()
        instruction = match.group(2).strip()
        message = generate_message(target, instruction)

        return {
            "action": "send",
            "target": target,
            "message": message,
            "send": not draft,
        }

    # write to dad about earthquake
    match = re.search(r"^(?:write|type)\s+to\s+(.+?)\s+(?:about|regarding)\s+(.+)$", command, re.IGNORECASE)
    if match:
        target = match.group(1).strip()
        topic = match.group(2).strip()
        message = generate_message(target, f"about {topic}")

        return {
            "action": "send",
            "target": target,
            "message": message,
            "send": not draft,
        }

    # message dad about earthquake
    match = re.search(r"^(?:msg|message|text)\s+(.+?)\s+(?:about|regarding)\s+(.+)$", command, re.IGNORECASE)
    if match:
        target = match.group(1).strip()
        topic = match.group(2).strip()
        message = generate_message(target, f"about {topic}")

        return {
            "action": "send",
            "target": target,
            "message": message,
            "send": not draft,
        }

    # msg dad hello
    # Better simple parser: target = first word after msg/message/text, rest = message.
    match = re.search(r"^(?:msg|message|text)\s+(\S+)\s+(.+)$", command, re.IGNORECASE)
    if match:
        target = match.group(1).strip()
        message = match.group(2).strip()

        # Remove optional saying/that.
        message = re.sub(r"^(saying|that)\s+", "", message, flags=re.IGNORECASE).strip()

        return {
            "action": "send",
            "target": target,
            "message": message,
            "send": not draft,
        }

    # call dad
    match = re.search(r"^(?:voice\s+call|call)\s+(.+)$", command, re.IGNORECASE)
    if match:
        return {
            "action": "call",
            "target": match.group(1).strip(),
            "video": False,
        }

    # video call dad
    match = re.search(r"^video\s+call\s+(.+)$", command, re.IGNORECASE)
    if match:
        return {
            "action": "call",
            "target": match.group(1).strip(),
            "video": True,
        }

    return {
        "action": "unknown",
        "command": original,
    }


# =========================================================
# CALL SUPPORT
# =========================================================

def start_call(target: str, video: bool = False) -> str:
    opened = open_chat(target)

    if not opened:
        return f"I could not open WhatsApp chat for '{target}'."

    sleep(0.6)

    if video:
        names = ["Video call", "video"]
    else:
        names = ["Voice call", "Audio call", "call"]

    for name in names:
        if click_ocr_text(name):
            return f"Started {'video' if video else 'voice'} call with {target}."

    return (
        f"I opened {target}'s chat, but I could not reliably click the "
        f"{'video' if video else 'voice'} call button."
    )


# =========================================================
# PUBLIC EXECUTOR API
# =========================================================

def execute_whatsapp_action(action: str, params: Optional[Dict[str, Any]] = None) -> str:
    params = ensure_dict(params)
    action = normalize(action)

    if action in ["whatsapp_open", "open_whatsapp"]:
        return open_whatsapp()

    if action in ["whatsapp_from_command", "whatsapp_command", "whatsapp_send_from_command"]:
        return run_command(
            params.get("command", "")
            or params.get("text", "")
            or params.get("input", "")
        )

    if action in ["whatsapp_send", "whatsapp_send_message"]:
        target = params.get("target", "") or params.get("to", "")
        message = params.get("message", "") or params.get("text", "")
        send = bool(params.get("send", True))
        return send_message_to_target(target, message, send=send)

    if action in ["whatsapp_draft", "whatsapp_draft_message"]:
        target = params.get("target", "") or params.get("to", "")
        message = params.get("message", "") or params.get("text", "")
        return send_message_to_target(target, message, send=False)

    if action in ["whatsapp_reply", "whatsapp_reply_current"]:
        message = params.get("message", "") or params.get("text", "")
        send = bool(params.get("send", True))
        return reply_current_chat(message, send=send)

    if action in ["whatsapp_save_contact", "save_whatsapp_contact"]:
        name = params.get("name", "")
        value = params.get("value", "") or params.get("phone", "")
        return save_contact_alias(name, value)

    if action in ["whatsapp_contacts", "show_whatsapp_contacts"]:
        return show_contacts()

    if action in ["whatsapp_pending", "whatsapp_pending_summary"]:
        return pending_summary()

    if action in ["whatsapp_send_pending"]:
        return send_pending()

    if action in ["whatsapp_cancel_pending", "whatsapp_discard_pending"]:
        clear_pending()
        return "Cancelled pending WhatsApp message."

    if action in ["whatsapp_call", "whatsapp_voice_call"]:
        target = params.get("target", "") or params.get("to", "")
        return start_call(target, video=False)

    if action in ["whatsapp_video_call"]:
        target = params.get("target", "") or params.get("to", "")
        return start_call(target, video=True)

    return f"Unknown WhatsApp action: {action}"


def run_command(command: str) -> str:
    command = compact_spaces(command)

    if not command:
        return "No WhatsApp command provided."

    approval = handle_whatsapp_approval_command(command)

    if approval:
        return approval

    parsed = parse_message_command(command)

    if not isinstance(parsed, dict):
        return "WhatsApp parser failed."

    action = parsed.get("action", "unknown")

    log(f"Parsed command: {parsed}")

    if action == "open":
        return open_whatsapp()

    if action == "save_contact":
        return save_contact_alias(parsed.get("name", ""), parsed.get("value", ""))

    if action == "show_contacts":
        return show_contacts()

    if action == "pending":
        return pending_summary()

    if action == "send_pending":
        return send_pending()

    if action == "cancel_pending":
        clear_pending()
        return "Cancelled pending WhatsApp message."

    if action == "reply":
        return reply_current_chat(
            parsed.get("message", ""),
            send=bool(parsed.get("send", True)),
        )

    if action == "send":
        target = parsed.get("target", "")
        message = parsed.get("message", "")
        send = bool(parsed.get("send", True))

        if send:
            return send_message_to_target(target, message, send=True)

        save_pending(target, message)
        return (
            "Drafted pending WhatsApp message.\n"
            f"To: {target}\n"
            f"Message: {message}\n"
            "Say 'send pending whatsapp' to send it."
        )

    if action == "call":
        return start_call(
            parsed.get("target", ""),
            video=bool(parsed.get("video", False)),
        )

    return (
        "I could not understand the WhatsApp command. Try:\n"
        "- msg dad hello\n"
        "- send hello to dad on whatsapp\n"
        "- ask dad how are you after earthquake\n"
        "- dad means +97798XXXXXXXX"
    )


# Compatibility aliases

def parse_whatsapp_command(command: str) -> Dict[str, Any]:
    return parse_message_command(command)


def whatsapp_command(command: str) -> str:
    return run_command(command)


# =========================================================
# HEALTH CHECK
# =========================================================

def health_check() -> str:
    checks = []

    checks.append(f"pyautogui: {'OK' if pyautogui else 'Missing'}")
    checks.append(f"pyperclip: {'OK' if pyperclip else 'Missing'}")
    checks.append(f"OpenAI message generation: {'OK' if client else 'Not available'}")
    checks.append(f"OCR: {'OK' if ocr_available() else 'Not available'}")
    checks.append(f"Front app: {frontmost_app_name() or 'Unknown'}")
    checks.append(f"WhatsApp active: {'Yes' if is_whatsapp_active() else 'No'}")
    checks.append(f"WhatsApp bounds: {get_whatsapp_window_bounds() or 'Not detected'}")

    return "\n".join(checks)


# =========================================================
# DIRECT TEST
# =========================================================

if __name__ == "__main__":
    print("=" * 60)
    print("HIMORA WHATSAPP AGENT - FINAL STABLE")
    print("=" * 60)
    print("Important:")
    print("- Spotlight search types ONLY the target name.")
    print("- Example: msg dad hello -> Spotlight searches: dad")
    print("=" * 60)
    print("Try:")
    print("- health")
    print("- open whatsapp")
    print("- dad means +97798XXXXXXXX")
    print("- show whatsapp contacts")
    print("- msg dad hello")
    print("- send hello to dad on whatsapp")
    print("- ask dad how are you after earthquake")
    print("- draft msg dad hello")
    print("- send pending whatsapp")
    print("- reply hello")
    print("- call dad")
    print("- video call dad")
    print("- exit")
    print("=" * 60)

    while True:
        try:
            user_command = input("\nwhatsapp command: ").strip()

            if user_command.lower() in ["exit", "quit"]:
                break

            if user_command.lower() == "health":
                print(health_check())
            else:
                print(run_command(user_command))

        except KeyboardInterrupt:
            print("\nStopped.")
            break

        except Exception as error:
            print("Error:", error)