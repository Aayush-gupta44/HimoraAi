"""
Himora main.py - Final Advanced Controller
------------------------------------------

This is the main controller for Himora.

It connects:
- ui.py              -> interface
- voice.py           -> listening / transcription
- speaker.py         -> short speech output
- router.py          -> voice command cleanup
- planner.py         -> task planning
- executor.py        -> executes Mac, WhatsApp, YouTube, Gmail, Screen actions
- screen_agent.py    -> reached through executor.py
- OpenAI             -> normal chat answers
- memory_data        -> local facts and chat history

Important behavior:
- No startup assistant message.
- Welcome screen stays visible on launch.
- Typed messages appear only once.
- Voice messages appear only once.
- Typed replies do not speak aloud.
- Voice replies speak shortly and then listener resumes.
- Screen commands route directly to executor.py as screen_from_command.
- Normal questions go to AI chat.
- Chat answers are short by default.
"""

import os
import re
import sys
import json
import time
import threading
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QThread, pyqtSignal, QTimer
except Exception as error:
    print("PyQt6 is required.")
    print("Install it with: python -m pip install PyQt6")
    raise error

try:
    from ui import HimoraUI
except Exception as error:
    print("[MAIN] Could not import HimoraUI from ui.py")
    raise error

try:
    from executor import execute
except Exception as error:
    execute = None
    print(f"[MAIN] executor.py import failed: {error}")

try:
    from planner import plan as planner_plan
except Exception as error:
    planner_plan = None
    print(f"[MAIN] planner.py import failed: {error}")

try:
    from router import route_input
except Exception as error:
    route_input = None
    print(f"[MAIN] router.py import failed: {error}")

try:
    from voice import listen
except Exception as error:
    listen = None
    print(f"[MAIN] voice.py import failed: {error}")

try:
    from speaker import speak
except Exception as error:
    speak = None
    print(f"[MAIN] speaker.py import failed: {error}")

try:
    from speaker import stop_speaking
except Exception:
    stop_speaking = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


# =========================================================
# PATHS / CONFIG
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory_data"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

MAIN_STATE_FILE = MEMORY_DIR / "main_state.json"
CHAT_MEMORY_FILE = MEMORY_DIR / "chat_memory.json"
FACT_MEMORY_FILE = MEMORY_DIR / "facts.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

CONFIG = {
    "chat_model": os.getenv("HIMORA_CHAT_MODEL", "gpt-4.1-mini"),
    "fallback_chat_model": os.getenv("HIMORA_FALLBACK_CHAT_MODEL", "gpt-4o-mini"),

    "max_chat_history": int(os.getenv("HIMORA_MAX_CHAT_HISTORY", "24")),
    "chat_max_tokens": int(os.getenv("HIMORA_CHAT_MAX_TOKENS", "500")),

    # Voice behavior
    "require_wake_word": os.getenv("HIMORA_REQUIRE_WAKE_WORD", "false").lower() == "true",
    "speak_after_voice": os.getenv("HIMORA_SPEAK_AFTER_VOICE", "true").lower() == "true",
    "voice_idle_sleep_ms": int(os.getenv("HIMORA_VOICE_IDLE_SLEEP_MS", "120")),
    "worker_cleanup_delay_ms": int(os.getenv("HIMORA_WORKER_CLEANUP_DELAY_MS", "600")),

    # Short chat behavior
    "short_chat_default": os.getenv("HIMORA_SHORT_CHAT_DEFAULT", "true").lower() == "true",

    "wake_words": [
        "himora",
        "hey himora",
        "hello himora",
        "hi himora",
        "okay himora",
        "ok himora",
    ],
}


# =========================================================
# BASIC HELPERS
# =========================================================

def log(message: str):
    print(f"[MAIN] {message}")


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
    except Exception as error:
        log(f"Could not read {path.name}: {error}")

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
        log(f"Could not write {path.name}: {error}")
        return False


def save_state(data: Dict[str, Any]):
    current = read_json(MAIN_STATE_FILE, {})

    if not isinstance(current, dict):
        current = {}

    current.update(data)
    current["updated_at"] = time.time()

    write_json(MAIN_STATE_FILE, current)


def remove_wake_word(text: str) -> Tuple[str, bool]:
    raw = compact_spaces(text)
    low = normalize(raw)

    for wake in sorted(CONFIG["wake_words"], key=len, reverse=True):
        wake_low = normalize(wake)

        if low == wake_low:
            return "", True

        if low.startswith(wake_low + " "):
            return raw[len(wake):].strip(" ,.!?:;"), True

    return raw, False


def estimate_speech_delay_ms(text: str) -> int:
    words = len(compact_spaces(text).split())

    if words <= 0:
        return 500

    return max(800, min(14000, int(words * 330)))


# =========================================================
# LOCAL MEMORY
# =========================================================

class LocalMemory:
    """
    Small local fact memory.

    Examples:
    - favorite color means blue
    - remember project name as Himora

    Phone/contact aliases with numbers are left for whatsapp_agent.py.
    """

    def __init__(self):
        self.path = FACT_MEMORY_FILE
        self.lock = threading.Lock()

    def key(self, text: str) -> str:
        text = normalize(text)
        text = re.sub(r"[^a-z0-9_]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        return text

    def load(self) -> Dict[str, str]:
        data = read_json(self.path, {})

        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}

        return {}

    def save(self, data: Dict[str, str]):
        write_json(self.path, data)

    def remember(self, name: str, value: str) -> str:
        name = compact_spaces(name)
        value = compact_spaces(value)

        if not name or not value:
            return "I need both the name and value to remember it."

        with self.lock:
            data = self.load()
            data[self.key(name)] = value
            self.save(data)

        return f"Got it. I will remember that {name} means {value}."

    def recall(self, name: str) -> str:
        name = compact_spaces(name)

        if not name:
            return ""

        with self.lock:
            data = self.load()

        return data.get(self.key(name), "")

    def facts_for_prompt(self, limit: int = 25) -> str:
        with self.lock:
            data = self.load()

        if not data:
            return "No saved local facts yet."

        items = list(data.items())[-limit:]
        lines = []

        for key, value in items:
            label = key.replace("_", " ")
            lines.append(f"- {label}: {value}")

        return "\n".join(lines)

    def handle_memory_command(self, user_input: str) -> Optional[str]:
        raw = compact_spaces(user_input)
        low = normalize(raw)

        if not raw:
            return None

        # Let WhatsApp handle phone aliases like "dad means 98..."
        phone_like = re.search(r"\+?\d[\d\s\-()]{6,}\d", raw)

        if phone_like and re.search(r"\b(means|remember|save)\b", low):
            return None

        patterns = [
            r"^(.+?)\s+means\s+(.+)$",
            r"^remember\s+(.+?)\s+as\s+(.+)$",
            r"^remember\s+(.+?)\s+is\s+(.+)$",
            r"^save\s+(.+?)\s+as\s+(.+)$",
        ]

        for pattern in patterns:
            match = re.search(pattern, raw, re.IGNORECASE)

            if match:
                left = match.group(1).strip()
                right = match.group(2).strip()

                if left and right and len(left.split()) <= 10:
                    return self.remember(left, right)

        recall_patterns = [
            r"^(?:what does)\s+(.+?)\s+(?:mean|means)\??$",
            r"^(?:what is|who is)\s+(.+?)\??$",
        ]

        for pattern in recall_patterns:
            match = re.search(pattern, raw, re.IGNORECASE)

            if match:
                key = match.group(1).strip(" ?.!,:;")
                value = self.recall(key)

                if value:
                    return f"{key} means {value}."

        if low in ["show memory", "show memories", "what do you remember"]:
            return self.facts_for_prompt()

        return None


# =========================================================
# CHAT ENGINE
# =========================================================

class ChatEngine:
    def __init__(self, memory: LocalMemory):
        self.memory = memory
        self.lock = threading.Lock()
        self.client = None

        if OpenAI and OPENAI_API_KEY:
            try:
                self.client = OpenAI(api_key=OPENAI_API_KEY)
            except Exception as error:
                log(f"OpenAI client failed: {error}")

    def load_history(self) -> List[Dict[str, str]]:
        data = read_json(CHAT_MEMORY_FILE, [])

        if not isinstance(data, list):
            return []

        cleaned = []

        for item in data:
            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = clean_text(item.get("content", ""))

            if role in ["user", "assistant"] and content:
                cleaned.append({"role": role, "content": content})

        return cleaned[-CONFIG["max_chat_history"]:]

    def save_turn(self, user_input: str, answer: str):
        with self.lock:
            history = self.load_history()
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": answer})
            history = history[-CONFIG["max_chat_history"]:]
            write_json(CHAT_MEMORY_FILE, history)

    def system_prompt(self) -> str:
        facts = self.memory.facts_for_prompt()

        short_rule = (
            "- Keep normal answers short: usually 1–3 short sentences.\n"
            "- Give details only when the user asks for full code, full explanation, or detailed steps."
            if CONFIG["short_chat_default"]
            else "- Give helpful answers with appropriate detail."
        )

        return f"""
You are Himora, Aayu's advanced desktop AI assistant.

You can:
- answer normal questions
- explain concepts
- help with coding
- help debug Himora
- write messages/emails
- help with startup/product planning

Important routing:
- Computer-control commands are handled by executor.py.
- Screen-reading commands are handled by screen_agent.py through executor.py.
- If the user asks to read/summarize/explain the screen, do not say you cannot access it. main.py should route it.

Style:
{short_rule}
- Be practical.
- Be direct.
- When helping with Himora code, give exact file names and exact code.
- Be honest when something depends on macOS permissions or app UI.

Saved local facts:
{facts}
""".strip()

    def answer(self, user_input: str) -> str:
        user_input = compact_spaces(user_input)

        if not user_input:
            return "I did not hear anything clearly."

        if self.client is None:
            return (
                "The OpenAI chat client is not available. "
                "Check your OPENAI_API_KEY in the .env file."
            )

        messages = [{"role": "system", "content": self.system_prompt()}]
        messages.extend(self.load_history())
        messages.append({"role": "user", "content": user_input})

        try:
            response = self.client.chat.completions.create(
                model=CONFIG["chat_model"],
                messages=messages,
                temperature=0.45,
                max_tokens=CONFIG["chat_max_tokens"],
            )

            answer = response.choices[0].message.content.strip()

        except Exception as first_error:
            log(f"Primary chat model failed: {first_error}")

            try:
                response = self.client.chat.completions.create(
                    model=CONFIG["fallback_chat_model"],
                    messages=messages,
                    temperature=0.45,
                    max_tokens=CONFIG["chat_max_tokens"],
                )

                answer = response.choices[0].message.content.strip()

            except Exception as second_error:
                log(f"Fallback chat model failed: {second_error}")
                answer = f"I could not generate a response: {second_error}"

        if answer:
            self.save_turn(user_input, answer)

        return answer


# =========================================================
# LOCAL RESPONSES / COMMAND DETECTION
# =========================================================

def help_text() -> str:
    return """
Try these:

Screen:
- read my screen
- explain what is going on my screen
- summarize this page
- summarize this pdf on screen
- read current page
- read right side of screen
- find error on screen
- inspect ui
- click Continue

Mac:
- volume 40
- volume up 20
- open bluetooth settings
- create folder Himora Test in desktop
- find file main.py

WhatsApp:
- msg dad hello
- message dad about earthquake
- ask dad how are you after earthquake

YouTube:
- open youtube and play shape of you
- pause the song

Gmail:
- open gmail
- compose gmail to someone@gmail.com about cyber fraud
""".strip()


def local_response(user_input: str) -> Optional[str]:
    low = normalize(user_input)

    if low in ["help", "commands", "what can you do"]:
        return help_text()

    if low in ["hello", "hi", "hey", "hlo"]:
        return "Hello, Aayu."

    return None


def is_screen_like_command(text: str) -> bool:
    """
    Critical routing.

    This catches all screen/pdf/browser/page commands before planner/chat.
    These commands should go directly:
    main.py -> executor.py -> screen_agent.py
    """

    low = normalize(text)

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
        "read current screen",
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
        "describe current window",
        "analyze window",
        "look at current window",
        "look at front window",

        "find error",
        "find error on screen",
        "find error in window",
        "find error in current window",
        "read error",
        "read error in window",
        "check error",
        "check errors",
        "what is the error",
        "what error is on screen",

        "inspect ui",
        "show ui elements",
        "visible elements",
        "list buttons",

        "suggest next action",
        "what should i do next",
        "what next",
        "help me with this screen",

        "read current page",
        "read browser",
        "read browser page",
        "summarize current page",
        "summarise current page",
    }

    if low in exact:
        return True

    starts = (
        "click ",
        "tap ",
        "double click ",
        "force click ",
        "force double click ",
        "wait for ",
        "find text ",
        "find button ",
    )

    if low.startswith(starts):
        return True

    screen_phrases = [
        "on screen",
        "my screen",
        "current screen",
        "front window",
        "current window",
        "this screen",
        "visible on screen",

        "explain what is going on my screen",
        "explain whats going on my screen",
        "explain what is on my screen",
        "what is going on my screen",
        "what's going on my screen",

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
        "summarize my screen",
        "summarise my screen",
        "summarize right side",
        "summarise right side",

        "read this pdf",
        "read this page",
        "read this article",
        "read right side",
        "read the right side",
        "read left side",
        "read center",
        "read middle",

        "explain this pdf",
        "explain this page",
        "explain this article",
        "explain right side",
        "explain left side",
        "explain center",
    ]

    return any(phrase in low for phrase in screen_phrases)


def is_hard_action_like_command(text: str) -> bool:
    """
    Extra safety route for obvious commands if planner/router misses them.
    """

    low = normalize(text)

    if is_screen_like_command(low):
        return True

    starters = (
        "open ",
        "close ",
        "quit ",
        "activate ",
        "launch ",
        "start ",
        "run ",
        "volume ",
        "set volume",
        "volume up",
        "volume down",
        "increase volume",
        "decrease volume",
        "wifi ",
        "wi-fi ",
        "bluetooth ",
        "open settings",
        "open bluetooth",
        "open wifi",
        "create folder",
        "make folder",
        "find file",
        "find folder",
        "open file",
        "open folder",
        "search finder",
        "spotlight ",
        "msg ",
        "message ",
        "text ",
        "reply ",
        "call ",
        "video call ",
        "voice call ",
        "compose gmail",
        "compose email",
        "open gmail",
        "open youtube",
        "play ",
        "pause the song",
        "resume the song",
        "change the song",
    )

    if low.startswith(starters):
        return True

    markers = [
        "whatsapp",
        "youtube",
        "gmail",
        "bluetooth",
        "wifi",
        "wi-fi",
        "system settings",
    ]

    return any(marker in low for marker in markers)


# =========================================================
# PLANNING PIPELINE
# =========================================================

def screen_executor_task(command: str, reason: str = "screen command direct route") -> Dict[str, Any]:
    command = compact_spaces(command)

    return {
        "type": "action",
        "cleaned_input": command,
        "task": {
            "type": "single",
            "action": "screen_from_command",
            "params": {
                "command": command,
            },
        },
        "reason": reason,
    }


def natural_executor_task(command: str, reason: str = "natural executor route") -> Dict[str, Any]:
    command = compact_spaces(command)

    return {
        "type": "action",
        "cleaned_input": command,
        "task": {
            "type": "single",
            "action": "natural_command",
            "params": {
                "command": command,
            },
        },
        "reason": reason,
    }


def route_and_plan(user_input: str) -> Dict[str, Any]:
    """
    Final decision system.

    Priority:
    1. Screen command direct route
    2. planner.py
    3. router.py
    4. hard action fallback
    5. chat fallback
    """

    original = compact_spaces(user_input)

    if not original:
        return {
            "type": "direct",
            "cleaned_input": "",
            "response": "I did not hear anything clearly.",
            "reason": "empty input",
        }

    # Most important: screen/page/pdf commands must never go to chat.
    if is_screen_like_command(original):
        return screen_executor_task(original)

    # Planner.
    if planner_plan:
        try:
            planned = planner_plan(original)

            if isinstance(planned, dict) and planned.get("type"):
                return planned

        except Exception as error:
            log(f"planner.plan failed: {error}")

    # Router.
    if route_input:
        try:
            routed = route_input(original)

            if isinstance(routed, dict):
                route_type = routed.get("type")
                cleaned = routed.get("cleaned_input") or routed.get("command") or original

                if is_screen_like_command(cleaned):
                    return screen_executor_task(cleaned, reason="screen command from router")

                if route_type == "direct":
                    return {
                        "type": "direct",
                        "cleaned_input": cleaned,
                        "response": routed.get("response", ""),
                        "reason": routed.get("reason", "router direct"),
                    }

                if route_type == "action":
                    return {
                        "type": "action",
                        "cleaned_input": cleaned,
                        "task": routed.get("task") or {
                            "type": "single",
                            "action": "natural_command",
                            "params": {"command": cleaned},
                        },
                        "reason": routed.get("reason", "router action"),
                    }

                return {
                    "type": "chat",
                    "cleaned_input": cleaned,
                    "reason": routed.get("reason", "router chat"),
                }

        except Exception as error:
            log(f"router.route_input failed: {error}")

    # Hard action fallback.
    if is_hard_action_like_command(original):
        return natural_executor_task(original, reason="hard action fallback")

    return {
        "type": "chat",
        "cleaned_input": original,
        "reason": "fallback chat",
    }


# =========================================================
# WORKER THREADS
# =========================================================

class HimoraWorker(QThread):
    result_ready = pyqtSignal(str, bool)
    status_ready = pyqtSignal(str)

    def __init__(
        self,
        user_input: str,
        is_voice: bool,
        chat_engine: ChatEngine,
        local_memory: LocalMemory,
    ):
        super().__init__()
        self.user_input = user_input
        self.is_voice = is_voice
        self.chat_engine = chat_engine
        self.local_memory = local_memory

    def run(self):
        try:
            raw_input = compact_spaces(self.user_input)
            command, had_wake_word = remove_wake_word(raw_input)

            if not command:
                if self.is_voice and CONFIG["require_wake_word"] and not had_wake_word:
                    self.result_ready.emit("", self.is_voice)
                    return

                self.result_ready.emit("I did not hear the command clearly.", self.is_voice)
                return

            if self.is_voice and CONFIG["require_wake_word"] and not had_wake_word:
                self.result_ready.emit("", self.is_voice)
                return

            save_state({
                "last_input": command,
                "last_raw_input": raw_input,
                "last_is_voice": self.is_voice,
            })

            local = local_response(command)

            if local:
                self.result_ready.emit(local, self.is_voice)
                return

            # Memory should not catch action commands.
            if not is_hard_action_like_command(command):
                memory_answer = self.local_memory.handle_memory_command(command)

                if memory_answer:
                    self.result_ready.emit(memory_answer, self.is_voice)
                    return

            planned = route_and_plan(command)
            planned_type = planned.get("type")
            cleaned_input = compact_spaces(planned.get("cleaned_input") or command)

            save_state({
                "last_planned_type": planned_type,
                "last_cleaned_input": cleaned_input,
                "last_plan_reason": planned.get("reason", ""),
            })

            if planned_type == "direct":
                self.result_ready.emit(clean_text(planned.get("response", "")), self.is_voice)
                return

            if planned_type == "action":
                self.status_ready.emit("Executing command...")

                if execute is None:
                    self.result_ready.emit("Executor is not available.", self.is_voice)
                    return

                task = planned.get("task")

                if not isinstance(task, dict):
                    if is_screen_like_command(cleaned_input):
                        task = {
                            "type": "single",
                            "action": "screen_from_command",
                            "params": {"command": cleaned_input},
                        }
                    else:
                        task = {
                            "type": "single",
                            "action": "natural_command",
                            "params": {"command": cleaned_input},
                        }

                result = execute(task)
                result = clean_text(result) or "Done."

                self.result_ready.emit(result, self.is_voice)
                return

            self.status_ready.emit("Thinking...")
            answer = self.chat_engine.answer(cleaned_input)
            self.result_ready.emit(clean_text(answer), self.is_voice)

        except Exception as error:
            traceback.print_exc()
            self.result_ready.emit(f"Something went wrong: {error}", self.is_voice)


class SpeakWorker(QThread):
    finished_speaking = pyqtSignal()

    def __init__(self, text: str):
        super().__init__()
        self.text = clean_text(text)

    def run(self):
        try:
            if speak and self.text:
                speak(self.text)
            else:
                time.sleep(estimate_speech_delay_ms(self.text) / 1000)

        except Exception as error:
            log(f"Speaking failed: {error}")

        finally:
            self.finished_speaking.emit()


class VoiceLoopWorker(QThread):
    command_ready = pyqtSignal(str)
    status_ready = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = True
        self._paused = False
        self.lock = threading.Lock()

    def stop(self):
        with self.lock:
            self._running = False
            self._paused = False

    def pause(self):
        with self.lock:
            self._paused = True

    def resume(self):
        with self.lock:
            self._paused = False

    def running(self) -> bool:
        with self.lock:
            return self._running

    def paused(self) -> bool:
        with self.lock:
            return self._paused

    def run(self):
        if listen is None:
            self.status_ready.emit("Voice engine is not available.")
            return

        self.status_ready.emit("Listening in background")

        while self.running():
            try:
                if self.paused():
                    self.msleep(CONFIG["voice_idle_sleep_ms"])
                    continue

                transcript = listen()
                transcript = compact_spaces(transcript)

                if not transcript:
                    self.msleep(CONFIG["voice_idle_sleep_ms"])
                    continue

                self.pause()
                self.command_ready.emit(transcript)

            except Exception as error:
                log(f"Voice loop error: {error}")
                self.status_ready.emit(f"Voice error: {error}")
                self.msleep(600)

        self.status_ready.emit("Ready")


# =========================================================
# MAIN APP
# =========================================================

class HimoraApp:
    def __init__(self):
        self.qt_app = QApplication.instance() or QApplication(sys.argv)

        self.local_memory = LocalMemory()
        self.chat_engine = ChatEngine(self.local_memory)

        self.ui = HimoraUI(
            send_callback=self.process_text,
            voice_callback=self.toggle_voice,
        )

        self.voice_mode = False
        self.voice_worker: Optional[VoiceLoopWorker] = None

        self.active_workers: List[HimoraWorker] = []
        self.speak_workers: List[SpeakWorker] = []

        # No startup add_message here.
        # This keeps your welcome screen clean.

        save_state({"app_started_at": time.time()})

    # -------------------------------------------------
    # UI SAFE METHODS
    # -------------------------------------------------

    def safe_add_message(self, text: str, is_user: bool):
        text = clean_text(text)

        if not text:
            return

        try:
            self.ui.add_message(text, is_user)
        except Exception as error:
            log(f"UI add_message failed: {error}")

    def safe_status(self, text: str):
        text = clean_text(text)

        if not text:
            return

        try:
            if hasattr(self.ui, "set_status"):
                self.ui.set_status(text)
        except Exception:
            pass

    def safe_mark_finished(self):
        try:
            if hasattr(self.ui, "mark_response_finished"):
                self.ui.mark_response_finished()
            elif hasattr(self.ui, "set_busy"):
                self.ui.set_busy(False)
        except Exception:
            pass

    def safe_set_voice_state(self, active: bool, status: Optional[str] = None):
        try:
            if hasattr(self.ui, "set_voice_state"):
                self.ui.set_voice_state(active, status=status)
        except TypeError:
            try:
                self.ui.set_voice_state(active)
            except Exception:
                pass
        except Exception:
            pass

    # -------------------------------------------------
    # TEXT INPUT
    # -------------------------------------------------

    def process_text(self, text: str):
        """
        Called by ui.py after UI already added the user's typed message.

        Return None.
        If this returns a string, current ui.py may add duplicate assistant replies.
        """

        text = compact_spaces(text)

        if not text:
            self.safe_mark_finished()
            return None

        if self.handle_app_level_command(text, from_voice=False):
            self.safe_mark_finished()
            return None

        self.start_worker(text, is_voice=False)
        return None

    def handle_app_level_command(self, text: str, from_voice: bool = False) -> bool:
        low = normalize(text)

        if low in ["clear chat", "clear screen", "new chat"]:
            try:
                if hasattr(self.ui, "clear_chat"):
                    self.ui.clear_chat()
            except Exception:
                pass

            return True

        if low in ["start voice", "voice mode", "turn on voice", "listen"]:
            self.start_voice_mode()

            if not from_voice:
                self.safe_add_message("Voice mode started.", is_user=False)

            return True

        if low in ["stop voice", "stop listening", "turn off voice", "sleep"]:
            self.stop_voice_mode()

            if not from_voice:
                self.safe_add_message("Voice mode stopped.", is_user=False)

            return True

        if low in ["stop speaking", "be quiet", "silence"]:
            if stop_speaking:
                stop_speaking()

            self.safe_status("Ready")
            return True

        return False

    # -------------------------------------------------
    # WORKERS
    # -------------------------------------------------

    def start_worker(self, text: str, is_voice: bool):
        worker = HimoraWorker(
            user_input=text,
            is_voice=is_voice,
            chat_engine=self.chat_engine,
            local_memory=self.local_memory,
        )

        worker.result_ready.connect(
            lambda response, voice_flag, w=worker: self.process_finished(
                response=response,
                is_voice=voice_flag,
                worker=w,
            )
        )

        worker.status_ready.connect(self.safe_status)
        worker.finished.connect(lambda w=worker: self.cleanup_worker(w))

        self.active_workers.append(worker)
        worker.start()

    def cleanup_worker(self, worker: HimoraWorker):
        def remove_worker():
            try:
                if worker in self.active_workers:
                    self.active_workers.remove(worker)
            except Exception:
                pass

        QTimer.singleShot(CONFIG["worker_cleanup_delay_ms"], remove_worker)

    def process_finished(self, response: str, is_voice: bool, worker: HimoraWorker):
        response = clean_text(response)

        if response:
            self.safe_add_message(response, is_user=False)

        if is_voice and self.voice_mode and CONFIG["speak_after_voice"]:
            if response:
                self.speak_then_resume(response)
            else:
                self.safe_mark_finished()
                self.resume_voice_listener()
        else:
            self.safe_mark_finished()

    # -------------------------------------------------
    # SPEAKING
    # -------------------------------------------------

    def speak_then_resume(self, text: str):
        text = clean_text(text)

        if not text:
            self.safe_mark_finished()
            self.resume_voice_listener()
            return

        speaker = SpeakWorker(text)
        speaker.finished_speaking.connect(lambda s=speaker: self.finish_speaking(s))
        self.speak_workers.append(speaker)
        speaker.start()

    def finish_speaking(self, speaker: SpeakWorker):
        try:
            if speaker in self.speak_workers:
                self.speak_workers.remove(speaker)
        except Exception:
            pass

        self.safe_mark_finished()
        self.resume_voice_listener()

    # -------------------------------------------------
    # VOICE MODE
    # -------------------------------------------------

    def toggle_voice(self, *args, **kwargs):
        if self.voice_mode:
            self.stop_voice_mode()
        else:
            self.start_voice_mode()

    def start_voice_mode(self):
        if self.voice_mode:
            self.safe_set_voice_state(True, status="Listening in background")
            return

        if listen is None:
            self.safe_add_message("Voice engine is not available.", is_user=False)
            self.safe_set_voice_state(False, status="Ready")
            return

        self.voice_mode = True
        self.safe_set_voice_state(True, status="Listening in background")
        save_state({"voice_mode": True})

        self.voice_worker = VoiceLoopWorker()
        self.voice_worker.command_ready.connect(self.process_voice_command)
        self.voice_worker.status_ready.connect(self.safe_status)
        self.voice_worker.start()

    def stop_voice_mode(self):
        self.voice_mode = False
        save_state({"voice_mode": False})

        if self.voice_worker:
            try:
                self.voice_worker.stop()
                self.voice_worker.wait(1400)
            except Exception:
                pass

            self.voice_worker = None

        self.safe_set_voice_state(False, status="Ready")

    def pause_voice_listener(self):
        if self.voice_worker:
            try:
                self.voice_worker.pause()
            except Exception:
                pass

    def resume_voice_listener(self):
        if self.voice_mode and self.voice_worker:
            try:
                self.voice_worker.resume()
            except Exception:
                pass

    def process_voice_command(self, transcript: str):
        transcript = compact_spaces(transcript)

        if not transcript:
            self.resume_voice_listener()
            return

        visible_text, _ = remove_wake_word(transcript)
        visible_text = visible_text or transcript

        low = normalize(visible_text)

        if low in ["stop", "stop listening", "turn off voice", "sleep"]:
            self.safe_add_message(visible_text, is_user=True)
            self.stop_voice_mode()
            self.safe_mark_finished()
            return

        if self.handle_app_level_command(visible_text, from_voice=True):
            self.safe_add_message(visible_text, is_user=True)
            self.safe_mark_finished()
            self.resume_voice_listener()
            return

        self.safe_add_message(visible_text, is_user=True)
        self.start_worker(transcript, is_voice=True)

    # -------------------------------------------------
    # RUN / SHUTDOWN
    # -------------------------------------------------

    def run(self):
        try:
            self.ui.show()
        except Exception as error:
            log(f"Could not show UI: {error}")
            raise

        exit_code = self.qt_app.exec()
        self.shutdown()
        sys.exit(exit_code)

    def shutdown(self):
        self.stop_voice_mode()

        if stop_speaking:
            try:
                stop_speaking()
            except Exception:
                pass

        for worker in list(self.active_workers):
            try:
                worker.quit()
                worker.wait(700)
            except Exception:
                pass

        for speaker in list(self.speak_workers):
            try:
                speaker.quit()
                speaker.wait(700)
            except Exception:
                pass

        save_state({"app_shutdown_at": time.time()})


# =========================================================
# ENTRY POINT
# =========================================================

def main():
    app = HimoraApp()
    app.run()


if __name__ == "__main__":
    main()