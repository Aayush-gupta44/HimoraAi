"""
Himora router.py v2
-------------------

Advanced voice/text command router for Himora.

Job:
- Clean messy voice commands.
- Fix common speech-recognition mistakes.
- Understand intent.
- Convert commands into executor-friendly natural commands.
- Keep normal questions as chat.

Used by main.py before sending anything to executor.py.

Examples:
"turn wife off" -> "wifi off"
"open blue tooth setting" -> "open bluetooth settings"
"send hello to dad on whatsapp" -> "msg dad hello"
"message dad saying hello" -> "msg dad hello"
"write to dad about earthquake" -> "message dad about earthquake"
"ask dad how are you after earth quack" -> "ask dad how are you after earthquake"
"play shape of you in you tube" -> "open youtube and play shape of you"
"make volume 40 percent" -> "volume 40"
"""

import re
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Tuple


# =========================================================
# BASIC HELPERS
# =========================================================
def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize(value: Any) -> str:
    return clean_text(value).lower()


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", clean_text(text)).strip()


def strip_punctuation_edges(text: str) -> str:
    return compact_spaces(text).strip(" .,!?:;\"'")


def remove_repeated_words(text: str) -> str:
    words = compact_spaces(text).split()
    if not words:
        return ""

    cleaned = []

    for word in words:
        if cleaned and normalize(cleaned[-1]) == normalize(word):
            continue
        cleaned.append(word)

    return " ".join(cleaned)


# =========================================================
# ROUTE RESULT
# =========================================================
@dataclass
class RouteResult:
    type: str
    original_input: str
    cleaned_input: str
    command: str = ""
    task: Optional[Dict[str, Any]] = None
    response: str = ""
    confidence: float = 0.0
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =========================================================
# NUMBER WORDS
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


# =========================================================
# VOICE NORMALIZATION
# =========================================================
PHRASE_REPLACEMENTS = [
    # Wake / assistant name variants
    (r"\bhey\s+himora\b", "himora"),
    (r"\bhello\s+himora\b", "himora"),
    (r"\bhi\s+himora\b", "himora"),

    # WhatsApp variants
    (r"\bwhat\s+sap\b", "whatsapp"),
    (r"\bwhat\s+sapp\b", "whatsapp"),
    (r"\bwhat's\s+up\b", "whatsapp"),
    (r"\bwats\s+app\b", "whatsapp"),
    (r"\bwatsapp\b", "whatsapp"),
    (r"\bwatsap\b", "whatsapp"),
    (r"\bwotapp\b", "whatsapp"),
    (r"\bwhats\s+app\b", "whatsapp"),

    # YouTube variants
    (r"\byou\s+tube\b", "youtube"),
    (r"\byoutub\b", "youtube"),
    (r"\butube\b", "youtube"),

    # Gmail/email variants
    (r"\bg\s+mail\b", "gmail"),
    (r"\bgee\s+mail\b", "gmail"),
    (r"\bjeemail\b", "gmail"),

    # Wi-Fi variants
    (r"\bwi\s*fi\b", "wifi"),
    (r"\bwi-fi\b", "wifi"),
    (r"\bwife\b", "wifi"),

    # Bluetooth variants
    (r"\bblue\s+tooth\b", "bluetooth"),
    (r"\bbluetuth\b", "bluetooth"),
    (r"\bblutooth\b", "bluetooth"),

    # System words
    (r"\bsetting\b", "settings"),
    (r"\bsystem setting\b", "system settings"),
    (r"\bvolium\b", "volume"),
    (r"\bvalume\b", "volume"),
    (r"\bbrightnesses\b", "brightness"),
    (r"\bspootlight\b", "spotlight"),

    # File/folder variants
    (r"\bfoulder\b", "folder"),
    (r"\bfolderr\b", "folder"),
    (r"\bphile\b", "file"),

    # App variants
    (r"\bvs\s+code\b", "vs code"),
    (r"\bv\s+s\s+code\b", "vs code"),
    (r"\bactivity\s+moniter\b", "activity monitor"),

    # Earthquake variants
    (r"\bearth\s+quack\b", "earthquake"),
    (r"\bearthquack\b", "earthquake"),
    (r"\bearth\s+quake\b", "earthquake"),
]


FILLER_PREFIXES = [
    "himora",
    "please",
    "can you please",
    "could you please",
    "would you please",
    "can you",
    "could you",
    "would you",
    "i want you to",
    "i need you to",
    "i want to",
    "please can you",
    "please could you",
    "hey",
]


def remove_filler_prefixes(text: str) -> str:
    text = compact_spaces(text)

    changed = True

    while changed:
        changed = False
        low = normalize(text)

        for prefix in sorted(FILLER_PREFIXES, key=len, reverse=True):
            if low == prefix:
                return ""

            if low.startswith(prefix + " "):
                text = text[len(prefix):].strip()
                changed = True
                break

    return compact_spaces(text)


def normalize_voice_text(text: str) -> str:
    text = strip_punctuation_edges(text)
    text = replace_number_words(text)

    for pattern, replacement in PHRASE_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    text = remove_repeated_words(text)
    text = remove_filler_prefixes(text)
    text = strip_punctuation_edges(text)

    return text


# =========================================================
# COMMAND CANONICALIZATION
# =========================================================
def canonicalize_volume(text: str) -> Optional[str]:
    low = normalize(text)

    match = re.search(
        r"^(?:set\s+)?(?:volume|sound)\s+(?:to\s+)?(\d+)\s*(?:percent|percentage|%)?$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"volume {match.group(1)}"

    match = re.search(
        r"^(?:make|keep)\s+(?:the\s+)?(?:volume|sound)\s+(\d+)\s*(?:percent|percentage|%)?$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"volume {match.group(1)}"

    match = re.search(
        r"^(?:turn\s+)?(?:volume|sound)\s+up(?:\s+by)?\s*(\d+)?\s*(?:percent|percentage|%)?$",
        text,
        re.IGNORECASE,
    )
    if match:
        amount = match.group(1) or "10"
        return f"volume up {amount}"

    match = re.search(
        r"^(?:increase)\s+(?:the\s+)?(?:volume|sound)(?:\s+by)?\s*(\d+)?\s*(?:percent|percentage|%)?$",
        text,
        re.IGNORECASE,
    )
    if match:
        amount = match.group(1) or "10"
        return f"volume up {amount}"

    match = re.search(
        r"^(?:turn\s+)?(?:volume|sound)\s+down(?:\s+by)?\s*(\d+)?\s*(?:percent|percentage|%)?$",
        text,
        re.IGNORECASE,
    )
    if match:
        amount = match.group(1) or "10"
        return f"volume down {amount}"

    match = re.search(
        r"^(?:decrease|reduce|lower)\s+(?:the\s+)?(?:volume|sound)(?:\s+by)?\s*(\d+)?\s*(?:percent|percentage|%)?$",
        text,
        re.IGNORECASE,
    )
    if match:
        amount = match.group(1) or "10"
        return f"volume down {amount}"

    if low in ["mute sound", "mute volume"]:
        return "mute"

    if low in ["unmute sound", "unmute volume"]:
        return "unmute"

    return None


def canonicalize_settings(text: str) -> Optional[str]:
    low = normalize(text)

    if low in ["open wifi", "open wifi setting", "open wifi settings"]:
        return "open wifi settings"

    if low in ["open bluetooth", "open bluetooth setting", "open bluetooth settings"]:
        return "open bluetooth settings"

    if low in ["wifi on", "turn wifi on", "enable wifi"]:
        return "wifi on"

    if low in ["wifi off", "turn wifi off", "disable wifi"]:
        return "wifi off"

    if low in ["bluetooth on", "turn bluetooth on", "enable bluetooth"]:
        return "bluetooth on"

    if low in ["bluetooth off", "turn bluetooth off", "disable bluetooth"]:
        return "bluetooth off"

    match = re.search(
        r"^(?:open|search)\s+(?:settings|system settings)\s+(?:for\s+)?(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"open settings {match.group(1).strip()}"

    match = re.search(
        r"^open\s+(.+?)\s+(?:setting|settings)$",
        text,
        re.IGNORECASE,
    )
    if match:
        subject = match.group(1).strip()
        return f"open settings {subject}"

    match = re.search(
        r"^(?:search|find)\s+(.+?)\s+(?:in\s+)?(?:settings|system settings)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"open settings {match.group(1).strip()}"

    return None


def canonicalize_files(text: str) -> Optional[str]:
    match = re.search(
        r"^(?:create|make)\s+(?:a\s+)?folder\s+(?:named\s+|called\s+)?(.+?)(?:\s+(?:in|on)\s+(desktop|downloads|documents|home|himora))?$",
        text,
        re.IGNORECASE,
    )
    if match:
        name = match.group(1).strip()
        location = match.group(2) or "desktop"
        return f"create folder {name} in {location}"

    match = re.search(
        r"^(?:find|search)\s+(?:the\s+)?(?:file)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"find file {match.group(1).strip()}"

    match = re.search(
        r"^(?:find|search)\s+(?:the\s+)?(?:folder|directory)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"find folder {match.group(1).strip()}"

    match = re.search(
        r"^open\s+(?:the\s+)?(?:file)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"open file {match.group(1).strip()}"

    match = re.search(
        r"^open\s+(?:the\s+)?(?:folder|directory)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"open folder {match.group(1).strip()}"

    match = re.search(
        r"^(?:search|find)\s+(?:in\s+)?finder\s+(?:for\s+)?(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"search finder {match.group(1).strip()}"

    return None


def canonicalize_youtube(text: str) -> Optional[str]:
    low = normalize(text)

    if low in ["open youtube", "youtube"]:
        return "open youtube"

    if low in ["pause song", "pause music", "pause youtube"]:
        return "pause the song"

    if low in ["resume song", "resume music", "resume youtube", "continue song"]:
        return "resume the song"

    if low in ["next song", "next video", "change song", "change the song"]:
        return "change the song"

    match = re.search(
        r"^(?:open\s+)?youtube\s+(?:and\s+)?play\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"open youtube and play {match.group(1).strip()}"

    match = re.search(
        r"^play\s+(.+?)\s+(?:on|in)\s+youtube$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"open youtube and play {match.group(1).strip()}"

    match = re.search(
        r"^play\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match and any(word in low for word in ["song", "music", "video", "youtube"]):
        return f"open youtube and play {match.group(1).strip()}"

    return None


def canonicalize_gmail(text: str) -> Optional[str]:
    low = normalize(text)

    if low in ["open gmail", "gmail", "open email"]:
        return "open gmail"

    match = re.search(
        r"^(?:write|compose|draft|create)\s+(?:an\s+)?(?:gmail|email|mail)\s+to\s+(.+?)\s+about\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"compose gmail to {match.group(1).strip()} about {match.group(2).strip()}"

    match = re.search(
        r"^(?:write|compose|draft|create)\s+(?:an\s+)?(?:gmail|email|mail)\s+about\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"compose gmail about {match.group(1).strip()}"

    if low in ["send it", "yes send it", "send email now", "discard email", "cancel email"]:
        return text

    return None


def canonicalize_whatsapp(text: str) -> Optional[str]:
    low = normalize(text)

    if low in ["open whatsapp", "whatsapp", "open whats"]:
        return "open whatsapp"

    # call dad on whatsapp -> call dad
    match = re.search(
        r"^(?:call|voice call)\s+(.+?)\s+(?:on|in)\s+whatsapp$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"call {match.group(1).strip()}"

    match = re.search(
        r"^video call\s+(.+?)\s+(?:on|in)\s+whatsapp$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"video call {match.group(1).strip()}"

    # whatsapp dad hello -> msg dad hello
    match = re.search(
        r"^whatsapp\s+(.+?)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        target = match.group(1).strip()
        message = match.group(2).strip()
        if target and message:
            return f"msg {target} {message}"

    # send hello to dad on whatsapp -> send hello to dad
    match = re.search(
        r"^send\s+(.+?)\s+to\s+(.+?)\s+(?:on|in)\s+whatsapp$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"send {match.group(1).strip()} to {match.group(2).strip()}"

    # send message to dad saying hello -> msg dad saying hello
    match = re.search(
        r"^send\s+(?:a\s+)?message\s+to\s+(.+?)\s+(?:saying|that|exactly)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"msg {match.group(1).strip()} saying {match.group(2).strip()}"

    # send dad hello -> msg dad hello
    match = re.search(
        r"^send\s+(.+?)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match and "gmail" not in low and "email" not in low:
        target = match.group(1).strip()
        message = match.group(2).strip()

        if target not in ["it", "email", "gmail", "mail"] and len(target.split()) <= 4:
            return f"msg {target} {message}"

    # message to dad hello -> msg dad hello
    match = re.search(
        r"^(?:message|msg|text)\s+to\s+(.+?)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"msg {match.group(1).strip()} {match.group(2).strip()}"

    # write to dad about earthquake -> message dad about earthquake
    match = re.search(
        r"^(?:write|type|send|message|msg|text)\s+to\s+(.+?)\s+about\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"message {match.group(1).strip()} about {match.group(2).strip()}"

    # ask dad how are you after earthquake -> keep same
    match = re.search(
        r"^ask\s+(.+?)\s+(how\s+.+|if\s+.+|whether\s+.+|are\s+.+|is\s+.+|can\s+.+|could\s+.+|would\s+.+|what\s+.+|why\s+.+|when\s+.+|where\s+.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"ask {match.group(1).strip()} {match.group(2).strip()}"

    if low.startswith(("msg ", "message ", "text ", "reply ", "call ", "voice call ", "video call ")):
        return text

    if low.startswith(("write about ", "type about ", "reply about ")):
        return text

    if low in [
        "approve whatsapp bulk send",
        "approve bulk send",
        "send whatsapp bulk",
        "cancel whatsapp bulk",
        "show pending whatsapp",
    ]:
        return text

    return None


def canonicalize_apps_and_web(text: str) -> Optional[str]:
    low = normalize(text)

    match = re.search(
        r"^(?:launch|start|run)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"open {match.group(1).strip()}"

    match = re.search(
        r"^(?:quit|exit)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"close {match.group(1).strip()}"

    if low.startswith(("open ", "close ", "activate ", "search ", "spotlight ")):
        return text

    return None


def canonicalize_command(text: str) -> str:
    text = normalize_voice_text(text)

    canonicalizers = [
        canonicalize_volume,
        canonicalize_settings,
        canonicalize_files,
        canonicalize_youtube,
        canonicalize_gmail,
        canonicalize_whatsapp,
        canonicalize_apps_and_web,
    ]

    for func in canonicalizers:
        result = func(text)
        if result:
            return compact_spaces(result)

    return text


# =========================================================
# ACTION DETECTION
# =========================================================
def is_probable_action(command: str) -> Tuple[bool, str, float]:
    low = normalize(command)

    if not low:
        return False, "empty", 0.0

    exact_actions = {
        "help",
        "commands",
        "open whatsapp",
        "open gmail",
        "open youtube",
        "pause the song",
        "resume the song",
        "change the song",
        "next song",
        "mute",
        "unmute",
        "screenshot",
        "front app",
        "bounds",
        "wifi on",
        "wifi off",
        "bluetooth on",
        "bluetooth off",
        "bluetooth status",
        "send it",
        "yes send it",
        "discard email",
        "cancel email",
        "approve whatsapp bulk send",
        "cancel whatsapp bulk",
        "show pending whatsapp",
    }

    if low in exact_actions:
        return True, "exact action", 0.99

    action_starters = (
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
        "msg ",
        "message ",
        "text ",
        "reply ",
        "call ",
        "voice call ",
        "video call ",
        "send ",
        "compose ",
        "draft ",
        "play ",
        "pause ",
        "resume ",
        "next ",
    )

    if low.startswith(action_starters):
        return True, "action starter", 0.92

    action_markers = [
        "whatsapp",
        "youtube",
        "gmail",
        "wifi",
        "bluetooth",
        "system settings",
        "settings",
        "finder",
        "spotlight",
    ]

    if any(marker in low for marker in action_markers):
        return True, "action marker", 0.86

    # Ask is only action if it looks like asking a person/contact.
    ask_match = re.search(
        r"^ask\s+([a-zA-Z0-9_ .'-]{1,40})\s+(how|if|whether|are|is|can|could|would|what|why|when|where)\b",
        command,
        re.IGNORECASE,
    )
    if ask_match:
        return True, "ask contact", 0.88

    return False, "chat", 0.25


# =========================================================
# PUBLIC ROUTER API
# =========================================================
def route_input(user_input: str) -> Dict[str, Any]:
    original = clean_text(user_input)
    cleaned = canonicalize_command(original)

    if not cleaned:
        return RouteResult(
            type="direct",
            original_input=original,
            cleaned_input="",
            response="I did not hear anything clearly.",
            confidence=0.9,
            reason="empty after cleaning",
        ).to_dict()

    low = normalize(cleaned)

    if low in ["help", "commands", "what can you do"]:
        return RouteResult(
            type="direct",
            original_input=original,
            cleaned_input=cleaned,
            response=help_text(),
            confidence=0.99,
            reason="help",
        ).to_dict()

    is_action, reason, confidence = is_probable_action(cleaned)

    if is_action:
        task = {
            "type": "single",
            "action": "natural_command",
            "params": {
                "command": cleaned,
                "original_command": original,
            },
        }

        return RouteResult(
            type="action",
            original_input=original,
            cleaned_input=cleaned,
            command=cleaned,
            task=task,
            confidence=confidence,
            reason=reason,
        ).to_dict()

    return RouteResult(
        type="chat",
        original_input=original,
        cleaned_input=cleaned,
        command=cleaned,
        confidence=confidence,
        reason=reason,
    ).to_dict()


def route_text(user_input: str) -> Dict[str, Any]:
    return route_input(user_input)


def route_command(user_input: str) -> Dict[str, Any]:
    return route_input(user_input)


def help_text() -> str:
    return """
Try saying:

Mac:
- volume 40
- volume up 20
- open bluetooth settings
- wifi off
- create folder Himora Test in desktop
- find file main.py

WhatsApp:
- msg dad hello
- send hello to dad on whatsapp
- message dad about earthquake
- ask dad how are you after earthquake

YouTube:
- play shape of you on youtube
- pause the song
- resume the song

Gmail:
- open gmail
- compose gmail to someone@gmail.com about cyber fraud
""".strip()


# =========================================================
# DIRECT TEST
# =========================================================
if __name__ == "__main__":
    print("=" * 60)
    print("HIMORA ROUTER TEST v2")
    print("=" * 60)
    print("Try:")
    print("- himora can you please turn the wife off")
    print("- open blue tooth setting")
    print("- send hello to dad on whatsapp")
    print("- message dad saying hello")
    print("- write to dad about earth quack")
    print("- ask dad how are you after earth quack")
    print("- play shape of you in you tube")
    print("- make volume forty percent")
    print("- create folder Test Project in desktop")
    print("- exit")
    print("=" * 60)

    while True:
        command = input("\nrouter command: ").strip()

        if command.lower() in ["exit", "quit"]:
            break

        result = route_input(command)
        print(json.dumps(result, indent=2, ensure_ascii=False))