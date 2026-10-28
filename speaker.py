"""
Himora speaker.py - Short Voice Speaker
---------------------------------------

Purpose:
- Speak less.
- Listen more.
- Never read long paragraphs aloud.
- Keep spoken replies short and natural.
- Full response still appears in UI; only voice output is shortened.

Used by main.py:
    from speaker import speak
    speak(response)

Features:
- Shortens long AI replies before speaking.
- Skips code blocks, OCR dumps, file lists, and long screen text.
- Speaks short confirmations for actions.
- Uses macOS 'say' first because it is reliable.
- Falls back to pyttsx3 if available.
"""

import os
import re
import time
import subprocess
from typing import Any, Optional


# =========================================================
# CONFIG
# =========================================================

CONFIG = {
    # Turn speech on/off globally.
    "enabled": os.getenv("HIMORA_SPEECH_ENABLED", "true").lower() == "true",

    # Main behavior.
    "speak_mode": os.getenv("HIMORA_SPEAK_MODE", "short").lower(),

    # Maximum spoken words.
    "max_words": int(os.getenv("HIMORA_SPEAK_MAX_WORDS", "22")),

    # macOS voice. Try: Samantha, Daniel, Alex, Karen
    "mac_voice": os.getenv("HIMORA_MAC_VOICE", "Samantha"),

    # Speech rate. Lower = slower. Good range: 165-210
    "rate": int(os.getenv("HIMORA_SPEAK_RATE", "185")),

    # If text is longer than this, speaker will summarize aggressively.
    "long_text_limit": int(os.getenv("HIMORA_LONG_SPEECH_LIMIT", "180")),
}


# =========================================================
# OPTIONAL PYTTSX3 FALLBACK
# =========================================================

try:
    import pyttsx3
except Exception:
    pyttsx3 = None


_engine = None


# =========================================================
# HELPERS
# =========================================================

def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", clean_text(text)).strip()


def normalize(text: str) -> str:
    return compact_spaces(text).lower()


def remove_markdown(text: str) -> str:
    text = clean_text(text)

    # Remove code blocks.
    text = re.sub(r"```[\s\S]*?```", " ", text)

    # Remove inline code marks.
    text = text.replace("`", "")

    # Remove markdown bullets/headers.
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)

    # Remove excessive symbols.
    text = text.replace("**", "")
    text = text.replace("__", "")
    text = text.replace("==", "")
    text = text.replace(">", "")

    return compact_spaces(text)


def word_count(text: str) -> int:
    return len(compact_spaces(text).split())


def first_sentence(text: str) -> str:
    text = compact_spaces(text)

    if not text:
        return ""

    parts = re.split(r"(?<=[.!?])\s+", text)

    for part in parts:
        part = compact_spaces(part)
        if part:
            return part

    return text


def limit_words(text: str, max_words: Optional[int] = None) -> str:
    max_words = max_words or CONFIG["max_words"]
    words = compact_spaces(text).split()

    if len(words) <= max_words:
        return " ".join(words)

    return " ".join(words[:max_words]).rstrip(".,;:") + "."


def has_many_lines(text: str) -> bool:
    lines = [line.strip() for line in clean_text(text).splitlines() if line.strip()]
    return len(lines) >= 5


def looks_like_code_or_log(text: str) -> bool:
    low = normalize(text)

    code_markers = [
        "traceback",
        "file ",
        "line ",
        "def ",
        "class ",
        "import ",
        "except ",
        "print(",
        "python ",
        "pip ",
        "brew ",
        "zsh:",
        "[executor]",
        "[main]",
        "[screen agent]",
    ]

    if any(marker in low for marker in code_markers):
        return True

    if "```" in text:
        return True

    return False


def looks_like_screen_dump(text: str) -> bool:
    low = normalize(text)

    screen_markers = [
        "visible text/ui elements",
        "i could not read any clear text",
        "screen recording permission",
        "found '",
        "at x=",
        "width=",
        "height=",
        "explorer",
        "outline",
        "timeline",
        "problems output debugconsole terminal",
    ]

    return any(marker in low for marker in screen_markers)


# =========================================================
# SPEECH SHORTENER
# =========================================================

def short_spoken_text(text: str) -> str:
    """
    Converts full assistant response into a very short spoken version.
    UI still shows full text; this only controls voice.
    """

    original = clean_text(text)

    if not original:
        return ""

    text = remove_markdown(original)
    low = normalize(text)

    # Direct action confirmations.
    if low in ["done", "done.", "ok", "okay", "completed", "success"]:
        return "Done."

    if "opened" in low or low.startswith("open "):
        return "Opened."

    if "clicked" in low:
        return "Clicked."

    if "pasted" in low:
        return "Pasted."

    if "typed" in low:
        return "Typed."

    if "sent" in low and "could be a sensitive action" not in low:
        return "Sent."

    if "voice mode started" in low:
        return "Voice mode on."

    if "voice mode stopped" in low:
        return "Voice mode off."

    # Screen/OCR responses.
    if "i did not detect any real runtime error" in low:
        return "No real error detected."

    if "visible runtime error lines" in low:
        return "I found a real error."

    if "could not read" in low and "screen" in low:
        return "I could not read the screen."

    if "check screen recording permission" in low:
        return "Check screen permission."

    if looks_like_screen_dump(text):
        return "I read the screen."

    # Sensitive action warning.
    if "could be a sensitive action" in low:
        return "That action needs confirmation."

    # Missing agent/module.
    if "is not available" in low:
        return first_sentence(text)

    # Long code/log/terminal text should not be spoken fully.
    if looks_like_code_or_log(text):
        return "I found technical details on screen."

    # Multi-line or long text.
    if has_many_lines(original):
        return limit_words(first_sentence(text), 16)

    if len(text) > CONFIG["long_text_limit"] or word_count(text) > CONFIG["max_words"]:
        return limit_words(first_sentence(text), CONFIG["max_words"])

    return limit_words(text, CONFIG["max_words"])


# =========================================================
# MACOS SAY ENGINE
# =========================================================

def stop_speaking():
    """
    Stops macOS say and pyttsx3 if possible.
    """

    try:
        subprocess.run(
            ["pkill", "-f", r"/usr/bin/say|say"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1,
        )
    except Exception:
        pass

    global _engine

    try:
        if _engine:
            _engine.stop()
    except Exception:
        pass


def speak_with_macos(text: str) -> bool:
    text = clean_text(text)

    if not text:
        return True

    try:
        command = [
            "say",
            "-v",
            CONFIG["mac_voice"],
            "-r",
            str(CONFIG["rate"]),
            text,
        ]

        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )

        return True

    except Exception:
        return False


def get_pyttsx3_engine():
    global _engine

    if pyttsx3 is None:
        return None

    if _engine is not None:
        return _engine

    try:
        _engine = pyttsx3.init()
        _engine.setProperty("rate", CONFIG["rate"])
        return _engine
    except Exception:
        return None


def speak_with_pyttsx3(text: str) -> bool:
    engine = get_pyttsx3_engine()

    if engine is None:
        return False

    try:
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception:
        return False


# =========================================================
# PUBLIC API
# =========================================================

def speak(text: str, force_full: bool = False) -> str:
    """
    Main function used by main.py.

    It speaks a shortened version by default.

    Returns the exact spoken text.
    """

    if not CONFIG["enabled"]:
        return ""

    text = clean_text(text)

    if not text:
        return ""

    if force_full or CONFIG["speak_mode"] == "full":
        spoken = remove_markdown(text)
    elif CONFIG["speak_mode"] == "off":
        return ""
    else:
        spoken = short_spoken_text(text)

    spoken = compact_spaces(spoken)

    if not spoken:
        return ""

    # Final safety limit.
    spoken = limit_words(spoken, CONFIG["max_words"])

    # Stop any old speech before speaking new text.
    stop_speaking()

    if speak_with_macos(spoken):
        return spoken

    if speak_with_pyttsx3(spoken):
        return spoken

    return ""


def say(text: str) -> str:
    return speak(text)


def speak_short(text: str) -> str:
    return speak(text, force_full=False)


def speak_full(text: str) -> str:
    return speak(text, force_full=True)


# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":
    tests = [
        "Done.",
        "I did not detect any real runtime error on the screen. Words like error inside source code are ignored.",
        "A black hole is a region in space where gravity is so strong that nothing, not even light, can escape from it. It forms when a massive star collapses.",
        "Visible text/UI elements:\n- Explorer at 12, 20\n- Terminal at 20, 600\n- screen_agent.py at 200, 40",
        "This action could be a sensitive action. Say force click Send if you really want me to click it.",
    ]

    for item in tests:
        spoken = short_spoken_text(item)
        print("FULL:", item)
        print("SPOKEN:", spoken)
        print("-" * 40)
        speak(item)
        time.sleep(0.3)