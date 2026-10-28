"""
Himora screen_agent.py - Final Advanced Screen Intelligence
-----------------------------------------------------------

Purpose:
- Read the screen intelligently, not randomly dump OCR.
- Summarize browser pages, PDFs, articles, and visible documents.
- Focus on useful screen areas such as browser/page/right side.
- Ignore Himora UI/sidebar noise when possible.
- Detect real runtime errors without confusing source code as errors.
- Find/click visible text or buttons safely.
- Support executor.py commands:
    read my screen
    explain what is going on my screen
    summarize this pdf on screen
    summarize this page
    read current page
    read right side of screen
    find error on screen
    inspect ui
    click Continue
    force click Send

Required Python packages:
python -m pip install pillow pytesseract pyautogui pyperclip python-dotenv openai

Required Homebrew:
brew install tesseract

Required macOS permissions:
System Settings -> Privacy & Security:
- Screen Recording
- Accessibility
- Input Monitoring
- Automation

For best Chrome page reading:
Chrome menu bar -> View -> Developer -> Allow JavaScript from Apple Events
"""

import os
import re
import io
import json
import time
import base64
import difflib
import subprocess
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple


# =========================================================
# ENV / OPTIONAL IMPORTS
# =========================================================

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
    from PIL import Image, ImageOps, ImageFilter, ImageEnhance
except Exception:
    Image = None
    ImageOps = None
    ImageFilter = None
    ImageEnhance = None


try:
    import pytesseract

    if Path("/opt/homebrew/bin/tesseract").exists():
        pytesseract.pytesseract.tesseract_cmd = "/opt/homebrew/bin/tesseract"
    elif Path("/usr/local/bin/tesseract").exists():
        pytesseract.pytesseract.tesseract_cmd = "/usr/local/bin/tesseract"

except Exception:
    pytesseract = None


try:
    from openai import OpenAI
except Exception:
    OpenAI = None


try:
    from mac_system import get_front_window_bounds
except Exception:
    get_front_window_bounds = None


try:
    from mac_system import get_frontmost_app
except Exception:
    get_frontmost_app = None


# =========================================================
# PATHS / CONFIG
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory_data"
SCREEN_DIR = MEMORY_DIR / "screen_agent"

MEMORY_DIR.mkdir(parents=True, exist_ok=True)
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

SCREEN_STATE_FILE = MEMORY_DIR / "screen_agent_state.json"
SCREEN_HISTORY_FILE = MEMORY_DIR / "screen_agent_history.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

CONFIG = {
    "vision_model": os.getenv("HIMORA_VISION_MODEL", "gpt-4o-mini"),

    # OCR
    "ocr_min_confidence": int(os.getenv("HIMORA_OCR_MIN_CONFIDENCE", "18")),
    "ocr_resize_factor": float(os.getenv("HIMORA_OCR_RESIZE_FACTOR", "1.8")),

    # Waiting / clicking
    "default_wait_timeout": int(os.getenv("HIMORA_SCREEN_WAIT_TIMEOUT", "10")),
    "click_after_delay": float(os.getenv("HIMORA_CLICK_DELAY", "0.25")),

    # Output control
    "max_ocr_lines_in_prompt": int(os.getenv("HIMORA_MAX_OCR_LINES", "120")),
    "max_extracted_text_chars": int(os.getenv("HIMORA_MAX_PAGE_TEXT_CHARS", "22000")),
    "max_history": 40,

    # Cropping
    "browser_right_crop_start": float(os.getenv("HIMORA_BROWSER_RIGHT_CROP_START", "0.34")),
    "center_crop_left": 0.12,
    "center_crop_top": 0.06,
    "center_crop_right": 0.94,
    "center_crop_bottom": 0.94,

    # Debug
    "save_debug_images": True,
}


client = None

if OpenAI and OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception as error:
        print(f"[SCREEN AGENT] OpenAI client failed: {error}")


# =========================================================
# DATA MODELS
# =========================================================

@dataclass
class ScreenBounds:
    left: int
    top: int
    width: int
    height: int
    scale_x: float = 1.0
    scale_y: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScreenLine:
    text: str
    x: int
    y: int
    w: int
    h: int
    confidence: float = 0.0

    @property
    def center(self) -> Tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScreenSnapshot:
    path: str
    bounds: ScreenBounds
    front_app: str = ""
    created_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "bounds": self.bounds.to_dict(),
            "front_app": self.front_app,
            "created_at": self.created_at,
        }


# =========================================================
# BASIC HELPERS
# =========================================================

def log(message: str):
    print(f"[SCREEN AGENT] {message}")


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
        log(f"Write JSON failed: {error}")
        return False


def save_state(data: Dict[str, Any]):
    current = read_json(SCREEN_STATE_FILE, {})

    if not isinstance(current, dict):
        current = {}

    current.update(data)
    current["updated_at"] = time.time()
    write_json(SCREEN_STATE_FILE, current)


def save_history(item: Dict[str, Any]):
    history = read_json(SCREEN_HISTORY_FILE, [])

    if not isinstance(history, list):
        history = []

    item["created_at"] = time.time()
    history.append(item)
    history = history[-CONFIG["max_history"]:]

    write_json(SCREEN_HISTORY_FILE, history)


def apple_quote(text: str) -> str:
    return json.dumps(str(text))


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


def fallback_frontmost_app() -> str:
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

    return run_osascript(script)


def current_front_app() -> str:
    if get_frontmost_app:
        try:
            app = get_frontmost_app()

            if isinstance(app, str) and app.strip():
                return app.strip()

            if isinstance(app, dict):
                return str(app.get("app") or app.get("name") or "").strip()

        except Exception:
            pass

    return fallback_frontmost_app()


def get_screen_size() -> Tuple[int, int]:
    if not pyautogui:
        return 0, 0

    size = pyautogui.size()
    return int(size.width), int(size.height)


def make_screenshot_path(prefix: str = "screen") -> Path:
    timestamp = int(time.time() * 1000)
    return SCREEN_DIR / f"{prefix}_{timestamp}.png"


def image_to_base64_data_url(img) -> str:
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def bounds_from_any(data: Any) -> Optional[Tuple[int, int, int, int]]:
    if not isinstance(data, dict):
        return None

    x = data.get("x", data.get("left"))
    y = data.get("y", data.get("top"))
    w = data.get("w", data.get("width"))
    h = data.get("h", data.get("height"))

    try:
        return int(x), int(y), int(w), int(h)
    except Exception:
        return None


def clamp_region(region: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    left, top, width, height = [int(v) for v in region]
    screen_w, screen_h = get_screen_size()

    left = max(0, left)
    top = max(0, top)

    if screen_w:
        width = min(width, max(1, screen_w - left))

    if screen_h:
        height = min(height, max(1, screen_h - top))

    return left, top, max(1, width), max(1, height)


def clean_extracted_page_text(text: str) -> str:
    text = clean_text(text)
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    noise_lines = [
        "donate",
        "create account",
        "log in",
        "article",
        "talk",
        "read",
        "edit",
        "view history",
        "tools",
        "appearance",
        "hide",
        "contents",
        "main page",
        "random article",
        "privacy policy",
        "terms of use",
    ]

    cleaned_lines = []

    for line in text.splitlines():
        line = compact_spaces(line)

        if not line:
            continue

        low = normalize(line)

        if len(line) <= 2:
            continue

        if low in noise_lines:
            continue

        if low.startswith("jump to"):
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


# =========================================================
# SCREENSHOT
# =========================================================

def capture_screen(
    front_window: bool = False,
    region: Optional[Tuple[int, int, int, int]] = None,
    save: bool = True,
) -> Tuple[Optional[Any], Optional[ScreenSnapshot]]:
    if not pyautogui or Image is None:
        return None, None

    if front_window and region is None:
        if get_front_window_bounds:
            try:
                raw_bounds = get_front_window_bounds()
                region = bounds_from_any(raw_bounds)
            except Exception:
                region = None

    if region:
        left, top, width, height = clamp_region(region)
        img = pyautogui.screenshot(region=(left, top, width, height))

        scale_x = img.width / max(1, width)
        scale_y = img.height / max(1, height)

        bounds = ScreenBounds(
            left=left,
            top=top,
            width=width,
            height=height,
            scale_x=scale_x,
            scale_y=scale_y,
        )
    else:
        logical_w, logical_h = get_screen_size()
        img = pyautogui.screenshot()

        scale_x = img.width / max(1, logical_w)
        scale_y = img.height / max(1, logical_h)

        bounds = ScreenBounds(
            left=0,
            top=0,
            width=logical_w,
            height=logical_h,
            scale_x=scale_x,
            scale_y=scale_y,
        )

    path = ""

    if save:
        file_path = make_screenshot_path("screen")
        img.save(file_path)
        path = str(file_path)

    snapshot = ScreenSnapshot(
        path=path,
        bounds=bounds,
        front_app=current_front_app(),
        created_at=time.time(),
    )

    save_state({"last_screenshot": snapshot.to_dict()})

    return img, snapshot


def take_screenshot(front_window: bool = False) -> str:
    img, snapshot = capture_screen(front_window=front_window, save=True)

    if not img or not snapshot:
        return "Could not take screenshot. Check Screen Recording permission."

    save_history(
        {
            "action": "screenshot",
            "front_window": front_window,
            "path": snapshot.path,
        }
    )

    return snapshot.path


# =========================================================
# OCR
# =========================================================

def ocr_available() -> bool:
    return bool(Image and ImageOps and pytesseract)


def preprocess_for_ocr(img):
    if img is None or ImageOps is None:
        return img

    try:
        processed = img.convert("L")
        processed = ImageOps.autocontrast(processed)

        if ImageEnhance:
            processed = ImageEnhance.Contrast(processed).enhance(1.35)
            processed = ImageEnhance.Sharpness(processed).enhance(1.15)

        if ImageFilter:
            processed = processed.filter(ImageFilter.SHARPEN)

        factor = float(CONFIG["ocr_resize_factor"])

        if factor and factor != 1:
            new_w = max(1, int(processed.width * factor))
            new_h = max(1, int(processed.height * factor))
            processed = processed.resize((new_w, new_h))

        return processed

    except Exception:
        return img


def ocr_lines_from_image(img, bounds: ScreenBounds) -> List[ScreenLine]:
    if not ocr_available() or img is None:
        return []

    processed = preprocess_for_ocr(img)

    resize_factor_x = processed.width / max(1, img.width)
    resize_factor_y = processed.height / max(1, img.height)

    try:
        data = pytesseract.image_to_data(
            processed,
            output_type=pytesseract.Output.DICT,
            config="--oem 3 --psm 6",
        )
    except Exception as error:
        log(f"OCR failed: {error}")
        return []

    grouped: Dict[Tuple[int, int, int], List[int]] = {}
    count = len(data.get("text", []))

    for i in range(count):
        word = clean_text(data["text"][i])

        if not word:
            continue

        try:
            confidence = float(data["conf"][i])
        except Exception:
            confidence = -1

        if confidence < CONFIG["ocr_min_confidence"]:
            continue

        key = (
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
        )

        grouped.setdefault(key, []).append(i)

    lines: List[ScreenLine] = []

    for indexes in grouped.values():
        words = []
        xs = []
        ys = []
        rights = []
        bottoms = []
        confs = []

        for i in indexes:
            word = clean_text(data["text"][i])

            if not word:
                continue

            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])

            words.append(word)
            xs.append(x)
            ys.append(y)
            rights.append(x + w)
            bottoms.append(y + h)

            try:
                confs.append(float(data["conf"][i]))
            except Exception:
                pass

        line_text = compact_spaces(" ".join(words))

        if not line_text:
            continue

        px1 = min(xs) / resize_factor_x
        py1 = min(ys) / resize_factor_y
        px2 = max(rights) / resize_factor_x
        py2 = max(bottoms) / resize_factor_y

        screen_x1 = bounds.left + int(px1 / max(0.001, bounds.scale_x))
        screen_y1 = bounds.top + int(py1 / max(0.001, bounds.scale_y))
        screen_x2 = bounds.left + int(px2 / max(0.001, bounds.scale_x))
        screen_y2 = bounds.top + int(py2 / max(0.001, bounds.scale_y))

        confidence = sum(confs) / max(1, len(confs))

        lines.append(
            ScreenLine(
                text=line_text,
                x=screen_x1,
                y=screen_y1,
                w=max(1, screen_x2 - screen_x1),
                h=max(1, screen_y2 - screen_y1),
                confidence=confidence,
            )
        )

    lines.sort(key=lambda line: (line.y, line.x))
    return lines


def get_screen_lines(front_window: bool = False) -> List[ScreenLine]:
    img, snapshot = capture_screen(front_window=front_window, save=True)

    if not img or not snapshot:
        return []

    lines = ocr_lines_from_image(img, snapshot.bounds)

    save_state(
        {
            "last_ocr_lines": [line.to_dict() for line in lines],
            "last_ocr_line_count": len(lines),
            "last_front_app": snapshot.front_app,
        }
    )

    return lines


def read_screen_text(front_window: bool = False) -> str:
    lines = get_screen_lines(front_window=front_window)

    if not lines:
        return "I could not read clear text from the screen. Check Screen Recording permission or OCR setup."

    text = "\n".join(line.text for line in lines)

    save_state(
        {
            "last_ocr_text": text,
            "last_ocr_line_count": len(lines),
        }
    )

    save_history(
        {
            "action": "read_screen",
            "front_window": front_window,
            "line_count": len(lines),
        }
    )

    return text


def read_focused_ocr_text(focus: str = "auto") -> str:
    img, snapshot = capture_screen(save=True)

    if not img or not snapshot:
        return "Could not capture the screen."

    cropped = crop_screen_by_focus(img, focus)
    crop_bounds = ScreenBounds(
        left=0,
        top=0,
        width=cropped.size[0],
        height=cropped.size[1],
        scale_x=1.0,
        scale_y=1.0,
    )

    lines = ocr_lines_from_image(cropped, crop_bounds)

    if not lines:
        return "I could not read clear text from that screen area."

    text = "\n".join(line.text for line in lines)
    return clean_extracted_page_text(text)


# =========================================================
# FOCUSED CROPPING
# =========================================================

def crop_screen_by_focus(img, focus: str = "auto"):
    if img is None:
        return None

    focus = normalize(focus)
    w, h = img.size

    if focus in ["right", "right side", "browser", "page", "article", "pdf", "document"]:
        start = CONFIG["browser_right_crop_start"]
        return img.crop((int(w * start), 0, w, h))

    if focus in ["left", "left side", "himora", "assistant"]:
        return img.crop((0, 0, int(w * 0.55), h))

    if focus in ["center", "middle", "main"]:
        return img.crop((
            int(w * CONFIG["center_crop_left"]),
            int(h * CONFIG["center_crop_top"]),
            int(w * CONFIG["center_crop_right"]),
            int(h * CONFIG["center_crop_bottom"]),
        ))

    if focus in ["top", "top side"]:
        return img.crop((0, 0, w, int(h * 0.55)))

    if focus in ["bottom", "bottom side", "terminal", "output"]:
        return img.crop((0, int(h * 0.45), w, h))

    return img


def choose_focus_from_request(user_request: str) -> str:
    low = normalize(user_request)

    if any(word in low for word in ["right side", "browser", "pdf", "page", "article", "website", "document"]):
        return "right"

    if any(word in low for word in ["terminal", "output", "console", "error"]):
        return "bottom"

    if any(word in low for word in ["left side", "himora", "sidebar"]):
        return "left"

    if any(word in low for word in ["center", "middle", "main content"]):
        return "center"

    return "center"


# =========================================================
# BROWSER / PAGE EXTRACTION
# =========================================================

def get_browser_info() -> Dict[str, str]:
    info = {
        "browser": "",
        "title": "",
        "url": "",
    }

    chrome_script = """
    tell application "Google Chrome"
        try
            if (count of windows) > 0 then
                set theTitle to title of active tab of front window
                set theURL to URL of active tab of front window
                return theTitle & "|||" & theURL
            end if
        on error
            return ""
        end try
    end tell
    """

    safari_script = """
    tell application "Safari"
        try
            if (count of windows) > 0 then
                set theTitle to name of current tab of front window
                set theURL to URL of current tab of front window
                return theTitle & "|||" & theURL
            end if
        on error
            return ""
        end try
    end tell
    """

    for browser, script in [("Google Chrome", chrome_script), ("Safari", safari_script)]:
        output = run_osascript(script)

        if "|||" in output:
            title, url = output.split("|||", 1)
            info["browser"] = browser
            info["title"] = clean_text(title)
            info["url"] = clean_text(url)
            return info

    return info


def extract_chrome_page_text() -> str:
    js = """
    (() => {
        function visibleTextFromBody() {
            const clone = document.body.cloneNode(true);
            const remove = clone.querySelectorAll(
                'script, style, nav, footer, header, aside, button, input, textarea, svg, noscript'
            );
            remove.forEach(el => el.remove());
            return clone.innerText || '';
        }

        try {
            return visibleTextFromBody();
        } catch (e) {
            return document.body ? document.body.innerText : '';
        }
    })();
    """

    script = f"""
    tell application "Google Chrome"
        try
            if (count of windows) > 0 then
                set pageText to execute active tab of front window javascript {apple_quote(js)}
                return pageText
            end if
        on error
            return ""
        end try
    end tell
    """

    return clean_text(run_osascript(script, timeout=12))


def extract_safari_page_text() -> str:
    js = """
    (() => {
        function visibleTextFromBody() {
            const clone = document.body.cloneNode(true);
            const remove = clone.querySelectorAll(
                'script, style, nav, footer, header, aside, button, input, textarea, svg, noscript'
            );
            remove.forEach(el => el.remove());
            return clone.innerText || '';
        }

        try {
            return visibleTextFromBody();
        } catch (e) {
            return document.body ? document.body.innerText : '';
        }
    })();
    """

    script = f"""
    tell application "Safari"
        try
            if (count of windows) > 0 then
                set pageText to do JavaScript {apple_quote(js)} in current tab of front window
                return pageText
            end if
        on error
            return ""
        end try
    end tell
    """

    return clean_text(run_osascript(script, timeout=12))


def extract_browser_page_text() -> Dict[str, str]:
    info = get_browser_info()
    text = ""

    if info.get("browser") == "Google Chrome":
        text = extract_chrome_page_text()

        if len(text) < 300:
            text = extract_safari_page_text()

    elif info.get("browser") == "Safari":
        text = extract_safari_page_text()

        if len(text) < 300:
            text = extract_chrome_page_text()

    else:
        text = extract_chrome_page_text()

        if len(text) < 300:
            text = extract_safari_page_text()

    text = clean_extracted_page_text(text)

    info["text"] = text
    return info


def page_text_is_useful(text: str) -> bool:
    text = clean_text(text)

    if len(text) < 300:
        return False

    low = normalize(text)

    # If it is mostly browser UI or menu text, reject.
    ui_noise = [
        "all bookmarks",
        "create account",
        "log in",
        "appearance",
        "tools",
        "view history",
    ]

    noise_hits = sum(1 for item in ui_noise if item in low)

    if noise_hits >= 4 and len(text) < 1200:
        return False

    return True


# =========================================================
# TEXT SUMMARY / VISION SUMMARY
# =========================================================

def summarize_text_content(text: str, user_request: str = "", title: str = "", url: str = "") -> str:
    text = clean_extracted_page_text(text)
    user_request = compact_spaces(user_request)

    if not text:
        return "I could not extract readable text from the page."

    text = text[:CONFIG["max_extracted_text_chars"]]

    if client is None:
        preview = text[:1800]
        return f"I extracted text, but OpenAI is not available for summarization.\n\n{preview}"

    prompt = f"""
You are Himora's advanced screen/page reading assistant.

User request:
{user_request or "Summarize the visible page or document."}

Page title:
{title}

URL:
{url}

Extracted text:
{text}

Task:
- Summarize the actual content.
- Ignore menus, buttons, sidebar text, bookmarks, navigation, and account/login text.
- If this is a PDF/article/document, explain the main topic and key points.
- If the user asks "what is going on", describe the visible useful content.
- Keep it clear and not too long.
- Use short paragraphs.
"""

    try:
        response = client.chat.completions.create(
            model=CONFIG["vision_model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.22,
        )

        answer = response.choices[0].message.content.strip()

        save_history(
            {
                "action": "summarize_text_content",
                "request": user_request,
                "title": title,
                "url": url,
                "answer": answer,
            }
        )

        return answer

    except Exception as error:
        return f"I extracted the text, but summarization failed: {error}"


def focused_screen_analysis(
    user_request: str = "",
    focus: str = "auto",
    front_window: bool = False,
) -> str:
    user_request = compact_spaces(user_request)
    focus = compact_spaces(focus or "auto")

    if not user_request:
        user_request = "Explain what is visible on the screen."

    low = normalize(user_request + " " + focus)

    wants_page_or_doc = any(
        phrase in low
        for phrase in [
            "pdf",
            "article",
            "page",
            "website",
            "browser",
            "document",
            "summarize",
            "summarise",
            "summary",
            "read this",
            "explain this",
            "current page",
        ]
    )

    # Best path: extract real browser page text.
    if wants_page_or_doc:
        browser_info = extract_browser_page_text()
        browser_text = clean_text(browser_info.get("text", ""))

        if page_text_is_useful(browser_text):
            return summarize_text_content(
                browser_text,
                user_request=user_request,
                title=browser_info.get("title", ""),
                url=browser_info.get("url", ""),
            )

    # Fallback: use screenshot + vision + focused OCR.
    if client is None:
        selected_focus = focus if focus != "auto" else choose_focus_from_request(user_request)
        return read_focused_ocr_text(selected_focus)

    img, snapshot = capture_screen(front_window=front_window, save=True)

    if not img or not snapshot:
        return "Could not capture the screen. Check Screen Recording permission."

    selected_focus = focus

    if selected_focus == "auto":
        selected_focus = choose_focus_from_request(user_request)

    cropped = crop_screen_by_focus(img, selected_focus)

    if cropped is None:
        cropped = img

    data_url = image_to_base64_data_url(cropped)

    try:
        crop_bounds = ScreenBounds(
            left=0,
            top=0,
            width=cropped.size[0],
            height=cropped.size[1],
            scale_x=1.0,
            scale_y=1.0,
        )

        lines = ocr_lines_from_image(cropped, crop_bounds)
        ocr_text = "\n".join(line.text for line in lines[:CONFIG["max_ocr_lines_in_prompt"]])
        ocr_text = clean_extracted_page_text(ocr_text)

    except Exception:
        ocr_text = ""

    browser_info = get_browser_info()

    final_prompt = f"""
You are Himora's advanced screen reader.

User request:
{user_request}

Focus area:
{selected_focus}

Front app:
{snapshot.front_app}

Browser title:
{browser_info.get("title", "")}

Browser URL:
{browser_info.get("url", "")}

OCR support text from the focused area:
{ocr_text}

Rules:
- Focus on the actual content the user likely wants.
- Ignore Himora's own chat/sidebar unless the user asks about Himora.
- If there is a webpage/article/PDF/document, summarize the main content.
- If this looks like Wikipedia/article content, summarize the article topic and important facts.
- If the content is partially hidden or OCR is imperfect, say that briefly.
- Do not dump random OCR text.
- Give a useful answer in short paragraphs.
"""

    try:
        response = client.chat.completions.create(
            model=CONFIG["vision_model"],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": final_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url,
                            },
                        },
                    ],
                }
            ],
            temperature=0.22,
        )

        answer = response.choices[0].message.content.strip()

        save_state(
            {
                "last_focused_analysis": answer,
                "last_focus": selected_focus,
                "last_screenshot": snapshot.to_dict(),
            }
        )

        save_history(
            {
                "action": "focused_screen_analysis",
                "request": user_request,
                "focus": selected_focus,
                "front_app": snapshot.front_app,
                "answer": answer,
            }
        )

        return answer

    except Exception as error:
        return f"Focused screen analysis failed: {error}"


def summarize_current_screen(user_request: str = "") -> str:
    return focused_screen_analysis(
        user_request=user_request or "Summarize the main useful content visible on the screen.",
        focus="auto",
        front_window=False,
    )


def summarize_browser_or_pdf(user_request: str = "") -> str:
    return focused_screen_analysis(
        user_request=user_request or "Summarize this PDF, article, or browser page.",
        focus="right",
        front_window=False,
    )


# =========================================================
# FIND / CLICK TEXT
# =========================================================

def similarity(a: str, b: str) -> float:
    a = normalize(a)
    b = normalize(b)

    if not a or not b:
        return 0.0

    return difflib.SequenceMatcher(None, a, b).ratio()


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", normalize(text))


def score_line_for_query(line_text: str, query: str) -> float:
    text = normalize(line_text)
    query = normalize(query)

    if not text or not query:
        return 0.0

    if query == text:
        return 1.0

    if query in text:
        return 0.95

    text_words = tokenize(text)
    query_words = tokenize(query)

    if not query_words:
        return similarity(text, query)

    hits = 0

    for word in query_words:
        if word in text_words or word in text:
            hits += 1
        else:
            best = max([similarity(word, tw) for tw in text_words] or [0.0])
            if best >= 0.78:
                hits += 0.75

    word_score = hits / max(1, len(query_words))
    seq_score = similarity(text, query)

    return max(word_score * 0.90, seq_score)


def find_text_on_screen(
    query: str,
    front_window: bool = False,
    threshold: float = 0.55,
) -> Optional[ScreenLine]:
    query = compact_spaces(query)

    if not query:
        return None

    lines = get_screen_lines(front_window=front_window)

    best_line = None
    best_score = 0.0

    for line in lines:
        score = score_line_for_query(line.text, query)

        if score > best_score:
            best_score = score
            best_line = line

    save_state(
        {
            "last_find_query": query,
            "last_find_score": best_score,
            "last_find_result": best_line.to_dict() if best_line else None,
        }
    )

    if best_line and best_score >= threshold:
        return best_line

    return None


DANGEROUS_CLICK_WORDS = [
    "delete",
    "erase",
    "remove",
    "trash",
    "discard",
    "format",
    "reset",
    "factory reset",
    "permanently",
    "confirm",
    "purchase",
    "buy",
    "pay",
    "payment",
    "send",
    "submit",
    "transfer",
    "withdraw",
    "install",
    "uninstall",
    "allow all",
    "grant access",
]


def is_potentially_dangerous_click(target: str) -> bool:
    low = normalize(target)
    return any(word in low for word in DANGEROUS_CLICK_WORDS)


def click_coordinates(x: int, y: int) -> str:
    if not pyautogui:
        return "Mouse control is not available."

    pyautogui.click(int(x), int(y))
    time.sleep(CONFIG["click_after_delay"])
    return f"Clicked at ({int(x)}, {int(y)})."


def click_text(
    query: str,
    front_window: bool = False,
    force: bool = False,
) -> str:
    query = compact_spaces(query)

    if not query:
        return "No text or button name provided."

    if is_potentially_dangerous_click(query) and not force:
        return (
            f"'{query}' could be a sensitive action. "
            f"Say 'force click {query}' if you really want me to click it."
        )

    if not pyautogui:
        return "Mouse control is not available."

    line = find_text_on_screen(query, front_window=front_window)

    if not line:
        return f"I could not find '{query}' on the screen."

    x, y = line.center
    pyautogui.click(x, y)
    time.sleep(CONFIG["click_after_delay"])

    save_history(
        {
            "action": "click_text",
            "query": query,
            "clicked": line.to_dict(),
            "force": force,
        }
    )

    return f"Clicked '{line.text}'."


def double_click_text(
    query: str,
    front_window: bool = False,
    force: bool = False,
) -> str:
    query = compact_spaces(query)

    if not query:
        return "No text provided."

    if is_potentially_dangerous_click(query) and not force:
        return (
            f"'{query}' could be a sensitive action. "
            f"Say 'force double click {query}' if you really want me to double-click it."
        )

    if not pyautogui:
        return "Mouse control is not available."

    line = find_text_on_screen(query, front_window=front_window)

    if not line:
        return f"I could not find '{query}' on the screen."

    x, y = line.center
    pyautogui.doubleClick(x, y)
    time.sleep(CONFIG["click_after_delay"])

    save_history(
        {
            "action": "double_click_text",
            "query": query,
            "clicked": line.to_dict(),
            "force": force,
        }
    )

    return f"Double-clicked '{line.text}'."


def wait_for_text(
    query: str,
    timeout: int = None,
    front_window: bool = False,
) -> str:
    query = compact_spaces(query)
    timeout = int(timeout or CONFIG["default_wait_timeout"])

    if not query:
        return "No text provided."

    start = time.time()

    while time.time() - start < timeout:
        line = find_text_on_screen(query, front_window=front_window, threshold=0.60)

        if line:
            return f"Found '{line.text}' on screen."

        time.sleep(0.7)

    return f"I did not find '{query}' within {timeout} seconds."


def paste_text(text: str) -> str:
    text = clean_text(text)

    if not text:
        return "No text provided."

    if pyperclip and pyautogui:
        pyperclip.copy(text)
        time.sleep(0.05)
        pyautogui.hotkey("command", "v")
        return "Pasted text."

    if pyautogui:
        pyautogui.write(text, interval=0.01)
        return "Typed text."

    return "Typing control is not available."


def click_text_and_type(query: str, text: str) -> str:
    result = click_text(query)

    if not result.startswith("Clicked"):
        return result

    time.sleep(0.25)
    typed = paste_text(text)

    return f"{result} {typed}"


# =========================================================
# REAL ERROR DETECTION
# =========================================================

STRONG_RUNTIME_ERROR_KEYWORDS = [
    "traceback",
    "modulenotfounderror",
    "attributeerror",
    "typeerror",
    "syntaxerror",
    "importerror",
    "nameerror",
    "valueerror",
    "filenotfounderror",
    "permissionerror",
    "keyerror",
    "indexerror",
    "runtimeerror",
    "zsh:",
    "command not found",
    "permission denied",
    "address already in use",
    "failed to start",
    "failed:",
    "fatal:",
    "exception:",
    "error:",
    "[error]",
    "segmentation fault",
    "crashed",
]

WEAK_ERROR_KEYWORDS = [
    "error",
    "exception",
    "failed",
    "failure",
    "warning",
    "invalid",
    "not found",
    "denied",
]

SOURCE_CODE_NOISE_PATTERNS = [
    r"^\s*try\s*:",
    r"^\s*except\b",
    r"^\s*finally\s*:",
    r"^\s*else\s*:",
    r"^\s*def\s+",
    r"^\s*class\s+",
    r"^\s*import\s+",
    r"^\s*from\s+.+\s+import\s+",
    r"^\s*if\s+__name__",
    r"^\s*print\s*\(",
    r"^\s*return\s+",
    r"^\s*raise\s+",
    r"^\s*log\s*\(",
    r"traceback\.print_exc",
    r"except\s+Exception\s+as\s+error",
    r"print\([\"']Error:",
    r"print\([\"']error:",
    r"f[\"'].*error.*[\"']",
    r"self\.",
    r"def\s+\w+\(",
    r"class\s+\w+",
]


def looks_like_source_code(line: str) -> bool:
    text = clean_text(line)
    low = normalize(text)

    if not text:
        return False

    for pattern in SOURCE_CODE_NOISE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    code_symbols = ["=", "(", ")", "{", "}", "[", "]", ":", "->"]

    if any(symbol in text for symbol in code_symbols):
        if any(word in low for word in ["error", "exception", "traceback"]):
            if not low.startswith(("traceback", "error:", "fatal:", "zsh:")):
                return True

    return False


def looks_like_terminal_error(line: str) -> bool:
    text = clean_text(line)
    low = normalize(text)

    if not text:
        return False

    if looks_like_source_code(text):
        return False

    for keyword in STRONG_RUNTIME_ERROR_KEYWORDS:
        if keyword in low:
            return True

    if re.search(r'File\s+"[^"]+",\s+line\s+\d+', text):
        return True

    if re.search(r"\b(error|warning|fatal):\s+.+", low):
        return True

    if any(keyword in low for keyword in WEAK_ERROR_KEYWORDS):
        terminal_markers = [
            "%",
            "$",
            "python ",
            "pip ",
            "brew ",
            "npm ",
            "uvicorn",
            "info:",
            "error:",
            "warning:",
        ]

        if any(marker in low for marker in terminal_markers):
            return True

    return False


def extract_error_lines(lines: List[ScreenLine]) -> List[str]:
    extracted = []

    for line in lines:
        text = compact_spaces(line.text)

        if looks_like_terminal_error(text):
            extracted.append(text)

    return extracted


def read_visible_errors(front_window: bool = False) -> str:
    lines = get_screen_lines(front_window=front_window)

    if not lines:
        return "I could not read text from the screen."

    error_lines = extract_error_lines(lines)
    full_text = "\n".join(line.text for line in lines)

    if not error_lines:
        return (
            "I did not detect any real runtime error on the screen. "
            "Words like 'error' inside source code are ignored."
        )

    error_text = "\n".join(error_lines)

    if client:
        prompt = f"""
The screen agent detected these likely real runtime error lines:

{error_text}

Full visible OCR text:

{full_text}

Important:
- Do not treat source code like print("Error:", error) or except Exception as error as a real error.
- Only analyze actual terminal/runtime/output errors.

Explain:
1. What the error means
2. The most likely cause
3. The exact next step to fix it

Keep it short and practical.
"""

        return analyze_screen(prompt=prompt, front_window=front_window, include_ocr=False)

    return "Visible runtime error lines:\n" + error_text


# =========================================================
# GENERAL VISION ANALYSIS
# =========================================================

def analyze_screen(
    prompt: str = "",
    front_window: bool = False,
    include_ocr: bool = True,
) -> str:
    prompt = compact_spaces(prompt)

    if client is None:
        if include_ocr:
            return read_screen_text(front_window=front_window)

        return "OpenAI vision is not available. Check OPENAI_API_KEY."

    img, snapshot = capture_screen(front_window=front_window, save=True)

    if not img or not snapshot:
        return "Could not capture the screen. Check Screen Recording permission."

    data_url = image_to_base64_data_url(img)

    ocr_block = ""

    if include_ocr:
        lines = ocr_lines_from_image(img, snapshot.bounds)
        visible_lines = [line.text for line in lines[:CONFIG["max_ocr_lines_in_prompt"]]]

        if visible_lines:
            ocr_block = "\nVisible OCR text:\n" + "\n".join(visible_lines)

    if not prompt:
        prompt = (
            "Describe what is on the screen. Identify the active app, useful content, "
            "visible errors, and what the user could do next."
        )

    final_prompt = f"""
You are Himora's screen intelligence agent.

Analyze the user's current screen.

Front app:
{snapshot.front_app}

User request:
{prompt}

OCR support:
{ocr_block}

Rules:
- Be concise and practical.
- Focus on useful content, not random UI noise.
- If there is an actual runtime error, explain the fix.
- If the word 'error' appears only inside source code, do not call it a real error.
- If the user is looking at an article/PDF/page, summarize the main content.
- Do not claim you clicked anything.
- If unsure, say what is uncertain.
"""

    try:
        response = client.chat.completions.create(
            model=CONFIG["vision_model"],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": final_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url,
                            },
                        },
                    ],
                }
            ],
            temperature=0.22,
        )

        answer = response.choices[0].message.content.strip()

        save_state(
            {
                "last_analysis": answer,
                "last_screenshot": snapshot.to_dict(),
            }
        )

        save_history(
            {
                "action": "analyze_screen",
                "front_window": front_window,
                "prompt": prompt,
                "answer": answer,
            }
        )

        return answer

    except Exception as error:
        log(f"Vision analysis failed: {error}")

        if include_ocr:
            return read_screen_text(front_window=front_window)

        return f"Vision analysis failed: {error}"


def suggest_next_action(front_window: bool = False) -> str:
    return focused_screen_analysis(
        user_request=(
            "Look at the screen and suggest the best next action. "
            "If there is an error, give the exact fix. "
            "If this is a page or document, explain what the user is looking at."
        ),
        focus="auto",
        front_window=front_window,
    )


def inspect_ui_elements(front_window: bool = False) -> str:
    lines = get_screen_lines(front_window=front_window)

    if not lines:
        return "I could not read UI text from the screen."

    important = []

    for line in lines:
        text = compact_spaces(line.text)

        if not text:
            continue

        if len(text) > 100:
            continue

        important.append(f"- {text} at ({line.x}, {line.y})")

    if not important:
        return "I could not identify clear UI elements."

    return "Visible text/UI elements:\n" + "\n".join(important[:100])


# =========================================================
# EXECUTOR API
# =========================================================

def execute_screen_action(action: str, params: Optional[Dict[str, Any]] = None) -> str:
    params = params or {}
    action = normalize(action)

    if action in ["screen_screenshot", "screenshot_screen"]:
        return take_screenshot(front_window=bool(params.get("front_window", False)))

    if action in ["screen_screenshot_front_window", "screenshot_front_window"]:
        return take_screenshot(front_window=True)

    if action in ["screen_read", "read_screen", "ocr_screen"]:
        return read_screen_text(front_window=bool(params.get("front_window", False)))

    if action in ["screen_read_smart", "smart_read_screen", "focused_read_screen"]:
        return focused_screen_analysis(
            user_request=params.get("prompt", "Read and explain the useful content on screen."),
            focus=params.get("focus", "auto"),
            front_window=bool(params.get("front_window", False)),
        )

    if action in ["screen_read_window", "read_front_window"]:
        return read_screen_text(front_window=True)

    if action in ["screen_errors", "read_errors", "find_errors"]:
        return read_visible_errors(front_window=bool(params.get("front_window", False)))

    if action in ["screen_analyze", "analyze_screen", "describe_screen"]:
        return focused_screen_analysis(
            user_request=params.get("prompt", "Explain what is visible on the screen."),
            focus=params.get("focus", "auto"),
            front_window=bool(params.get("front_window", False)),
        )

    if action in ["screen_summarize", "summarize_screen"]:
        return summarize_current_screen(params.get("prompt", ""))

    if action in ["screen_summarize_page", "summarize_page", "summarize_pdf"]:
        return summarize_browser_or_pdf(params.get("prompt", ""))

    if action in ["screen_suggest", "suggest_next_action"]:
        return suggest_next_action(front_window=bool(params.get("front_window", False)))

    if action in ["screen_find_text", "find_text"]:
        line = find_text_on_screen(
            params.get("query", ""),
            front_window=bool(params.get("front_window", False)),
            threshold=float(params.get("threshold", 0.55)),
        )

        if not line:
            return f"I could not find '{params.get('query', '')}' on the screen."

        return json.dumps(line.to_dict(), indent=2, ensure_ascii=False)

    if action in ["screen_click_text", "click_text", "click_button"]:
        return click_text(
            params.get("query", ""),
            front_window=bool(params.get("front_window", False)),
            force=bool(params.get("force", False)),
        )

    if action in ["screen_double_click_text", "double_click_text"]:
        return double_click_text(
            params.get("query", ""),
            front_window=bool(params.get("front_window", False)),
            force=bool(params.get("force", False)),
        )

    if action in ["screen_wait_for_text", "wait_for_text"]:
        return wait_for_text(
            params.get("query", ""),
            timeout=int(params.get("timeout", CONFIG["default_wait_timeout"])),
            front_window=bool(params.get("front_window", False)),
        )

    if action in ["screen_click_and_type", "click_and_type"]:
        return click_text_and_type(
            params.get("query", ""),
            params.get("text", ""),
        )

    if action in ["screen_ui_elements", "inspect_ui", "visible_elements"]:
        return inspect_ui_elements(front_window=bool(params.get("front_window", False)))

    if action in ["screen_from_command", "screen_command"]:
        return run_command(
            params.get("command", "")
            or params.get("text", "")
            or params.get("input", "")
        )

    return f"Unknown screen action: {action}"


# =========================================================
# NATURAL COMMAND PARSER
# =========================================================

def is_page_summary_command(low: str) -> bool:
    phrases = [
        "summarize this pdf",
        "summarise this pdf",
        "summarize pdf",
        "summarise pdf",
        "summarize this page",
        "summarise this page",
        "summarize page",
        "summarise page",
        "summarize article",
        "summarise article",
        "summarize document",
        "summarise document",
        "read this pdf",
        "read this page",
        "read this article",
        "explain this pdf",
        "explain this page",
        "explain this article",
        "read browser",
        "read browser page",
        "read current page",
        "summarize current page",
        "summarise current page",
    ]

    return any(phrase in low for phrase in phrases)


def is_screen_explanation_command(low: str) -> bool:
    phrases = [
        "explain what is going on my screen",
        "explain whats going on my screen",
        "explain what is on my screen",
        "what is going on my screen",
        "what's going on my screen",
        "summarize my screen",
        "summarise my screen",
        "explain screen",
        "explain my screen",
    ]

    return any(phrase in low for phrase in phrases)


def run_command(command: str) -> str:
    command = compact_spaces(command)
    low = normalize(command)

    if not command:
        return "No screen command provided."

    # Smart page/PDF/document reading.
    if is_page_summary_command(low):
        return summarize_browser_or_pdf(command)

    if is_screen_explanation_command(low):
        return summarize_current_screen(command)

    if any(phrase in low for phrase in [
        "read right side",
        "read the right side",
        "explain right side",
        "summarize right side",
        "summarise right side",
        "right side of screen",
    ]):
        return focused_screen_analysis(command, focus="right")

    if any(phrase in low for phrase in [
        "read left side",
        "read the left side",
        "explain left side",
        "summarize left side",
        "summarise left side",
        "left side of screen",
    ]):
        return focused_screen_analysis(command, focus="left")

    if any(phrase in low for phrase in [
        "read center",
        "read middle",
        "explain center",
        "summarize center",
        "summarise center",
        "main content",
    ]):
        return focused_screen_analysis(command, focus="center")

    # Screenshots.
    if low in ["screenshot", "take screenshot", "capture screen"]:
        return take_screenshot(front_window=False)

    if low in ["screenshot window", "take screenshot of window", "capture front window"]:
        return take_screenshot(front_window=True)

    # Raw OCR commands.
    if low in ["ocr screen", "raw read screen", "raw screen text"]:
        return read_screen_text(front_window=False)

    if low in ["read screen", "read my screen", "what text is on screen"]:
        return focused_screen_analysis(
            user_request="Read and explain the useful content on the screen. Do not dump random OCR.",
            focus="auto",
            front_window=False,
        )

    if low in ["read window", "read front window", "read current window"]:
        return focused_screen_analysis(
            user_request="Read and explain the useful content in the current window.",
            focus="auto",
            front_window=True,
        )

    # Smart describe commands.
    if low in [
        "describe screen",
        "describe my screen",
        "analyze screen",
        "what is on my screen",
        "look at screen",
        "look at my screen",
    ]:
        return focused_screen_analysis(command, focus="auto", front_window=False)

    if low in [
        "describe window",
        "analyze window",
        "look at current window",
        "look at front window",
        "describe current window",
    ]:
        return focused_screen_analysis(command, focus="auto", front_window=True)

    # Errors.
    if low in [
        "find error",
        "read error",
        "what error is on screen",
        "what is the error",
        "check error",
        "check errors",
        "find error on screen",
    ]:
        return read_visible_errors(front_window=False)

    if low in [
        "find error in window",
        "read error in window",
        "check current window error",
        "find error in current window",
    ]:
        return read_visible_errors(front_window=True)

    # Suggestions.
    if low in [
        "suggest next action",
        "what should i do next",
        "what next",
        "help me with this screen",
    ]:
        return suggest_next_action(front_window=False)

    # Inspect UI.
    if low in ["inspect ui", "show ui elements", "visible elements", "list buttons"]:
        return inspect_ui_elements(front_window=False)

    # Click coordinates.
    coord_match = re.search(r"^click\s+(-?\d+)\s+(-?\d+)$", command, re.IGNORECASE)
    if coord_match:
        return click_coordinates(int(coord_match.group(1)), int(coord_match.group(2)))

    # Force click.
    force_double = re.search(r"^force\s+double\s+click\s+(.+)$", command, re.IGNORECASE)
    if force_double:
        return double_click_text(force_double.group(1).strip(), force=True)

    force_click = re.search(r"^force\s+click\s+(.+)$", command, re.IGNORECASE)
    if force_click:
        return click_text(force_click.group(1).strip(), force=True)

    # Double click.
    double_click_match = re.search(r"^double\s+click\s+(.+)$", command, re.IGNORECASE)
    if double_click_match:
        return double_click_text(double_click_match.group(1).strip())

    # Click and type.
    type_match = re.search(
        r"^click\s+(.+?)\s+and\s+(?:type|write|paste)\s+(.+)$",
        command,
        re.IGNORECASE,
    )
    if type_match:
        return click_text_and_type(
            type_match.group(1).strip(),
            type_match.group(2).strip(),
        )

    # Click visible text.
    click_match = re.search(r"^(?:click|press|tap)\s+(.+)$", command, re.IGNORECASE)
    if click_match:
        return click_text(click_match.group(1).strip())

    # Wait.
    wait_match = re.search(r"^wait\s+for\s+(.+)$", command, re.IGNORECASE)
    if wait_match:
        return wait_for_text(wait_match.group(1).strip())

    # Find text.
    find_text_match = re.search(r"^(?:find text|find button|find)\s+(.+)$", command, re.IGNORECASE)
    if find_text_match:
        query = find_text_match.group(1).strip()
        line = find_text_on_screen(query)

        if not line:
            return f"I could not find '{query}' on the screen."

        return (
            f"Found '{line.text}' at x={line.x}, y={line.y}, "
            f"width={line.w}, height={line.h}."
        )

    # Final fallback: focused screen analysis.
    return focused_screen_analysis(command, focus="auto", front_window=False)


# =========================================================
# HEALTH CHECK
# =========================================================

def health_check() -> str:
    checks = []

    checks.append(f"pyautogui: {'OK' if pyautogui else 'Missing'}")
    checks.append(f"PIL/Pillow: {'OK' if Image else 'Missing'}")
    checks.append(f"pytesseract: {'OK' if pytesseract else 'Missing'}")
    checks.append(f"OpenAI vision: {'OK' if client else 'Not available'}")

    try:
        img, snapshot = capture_screen(save=False)
        checks.append(f"screen capture: {'OK' if img and snapshot else 'Failed'}")
    except Exception as error:
        checks.append(f"screen capture: Failed ({error})")

    browser = get_browser_info()
    checks.append(f"browser: {browser.get('browser') or 'Not detected'}")

    if browser.get("title"):
        checks.append(f"browser title: {browser.get('title')}")

    if browser.get("url"):
        checks.append(f"browser url: {browser.get('url')}")

    return "\n".join(checks)


# =========================================================
# DIRECT TEST
# =========================================================

if __name__ == "__main__":
    print("=" * 60)
    print("HIMORA SCREEN AGENT TEST - FINAL ADVANCED")
    print("=" * 60)
    print("Try:")
    print("- health")
    print("- read screen")
    print("- read my screen")
    print("- explain what is going on my screen")
    print("- summarize this pdf on screen")
    print("- summarize this page")
    print("- read current page")
    print("- read right side of screen")
    print("- describe screen")
    print("- find error")
    print("- inspect ui")
    print("- click Continue")
    print("- force click Send")
    print("- wait for Done")
    print("- what should i do next")
    print("- raw read screen")
    print("- exit")
    print("=" * 60)

    while True:
        try:
            command = input("\nscreen_agent command: ").strip()

            if command.lower() in ["exit", "quit"]:
                break

            if command.lower() == "health":
                print(health_check())
            else:
                print(run_command(command))

        except KeyboardInterrupt:
            print("\nStopped.")
            break

        except Exception as error:
            print("Error:", error)