"""
Himora v3.5 Advanced Voice Engine
---------------------------------

This file handles:
- High-quality microphone recording
- Voice activity detection
- Background listening
- OpenAI transcription
- Google fallback transcription
- Wake word support
- Multilingual speech input
- Better handling of noisy rooms
- Better handling of misheard app names like "wotapp" -> "whatsapp"

This file does NOT control UI wave animation.
main.py and ui.py control wave ON/OFF state.

Important:
Your old SpeechRecognition error:
Bad CPU type in executable: flac-mac

is avoided here because the primary recording/transcription system
does not depend on SpeechRecognition's bundled flac-mac binary.
"""

import os
import re
import time
import wave
import tempfile
import threading
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any

from dotenv import load_dotenv

load_dotenv()


# =========================================================
# OPTIONAL IMPORTS
# =========================================================
try:
    import numpy as np
except Exception:
    np = None

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    import speech_recognition as sr
except Exception:
    sr = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


# =========================================================
# SYSTEM PATH FIX
# =========================================================
# Helps SpeechRecognition fallback find Homebrew flac instead of
# using its broken bundled flac-mac binary.
os.environ["PATH"] = (
    "/opt/homebrew/bin:"
    "/usr/local/bin:"
    + os.environ.get("PATH", "")
)


# =========================================================
# GLOBAL CONFIG
# =========================================================
MIC_INDEX = None

WAKE_WORDS = [
    "himora",
    "hey himora",
    "hello himora",
    "hi himora",
]

STOP_WORDS = [
    "stop listening",
    "turn off voice",
    "voice off",
    "stop himora",
]

VOICE_CONFIG: Dict[str, Any] = {
    # Primary transcription engine:
    # openai = best for your Himora
    # google = fallback
    # auto = try openai then google
    "engine": os.getenv("HIMORA_STT_ENGINE", "auto"),

    # OpenAI transcription model.
    # Keep configurable so you can change it from .env later.
    "openai_model": os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe"),
    "openai_fallback_model": os.getenv("OPENAI_TRANSCRIBE_FALLBACK_MODEL", "whisper-1"),

    # Audio quality
    "sample_rate": 16000,
    "channels": 1,
    "block_ms": 40,

    # Listening behavior
    "ambient_duration": 0.75,
    "timeout": 7.0,
    "phrase_time_limit": 16.0,
    "silence_duration": 0.90,
    "min_record_seconds": 0.45,

    # Noise detection
    "threshold_multiplier": 3.2,
    "min_voice_rms": 0.010,
    "max_voice_rms": 0.090,

    # Retry should be low because main.py already loops continuously.
    "retry_attempts": 1,

    # Debug
    "save_debug_audio": False,
    "debug_dir": "voice_debug",
}


# =========================================================
# OPENAI CLIENT
# =========================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = None

if OpenAI and OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        client = None


# =========================================================
# LOGGER
# =========================================================
def log(message: str):
    print(f"[VOICE ENGINE] {message}")


# =========================================================
# BASIC HELPERS
# =========================================================
def safe_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize(text: str) -> str:
    return safe_text(text).lower()


def now() -> float:
    return time.time()


def ensure_debug_dir() -> Path:
    path = Path(VOICE_CONFIG["debug_dir"])
    path.mkdir(parents=True, exist_ok=True)
    return path


# =========================================================
# MICROPHONE HELPERS
# =========================================================
def list_microphones() -> List[str]:
    """
    Prints and returns available microphones.
    Works with sounddevice primarily.
    """
    names: List[str] = []

    print("=" * 50)
    print("HIMORA MICROPHONE DEVICES")
    print("=" * 50)

    if sd:
        try:
            devices = sd.query_devices()

            for index, device in enumerate(devices):
                if device.get("max_input_channels", 0) > 0:
                    name = device.get("name", f"Input Device {index}")
                    names.append(name)
                    print(f"{index}: {name}")

            if not names:
                print("No input microphones found by sounddevice.")

        except Exception as error:
            print(f"sounddevice device listing failed: {error}")

    elif sr:
        try:
            names = sr.Microphone.list_microphone_names()

            for index, name in enumerate(names):
                print(f"{index}: {name}")

        except Exception as error:
            print(f"SpeechRecognition device listing failed: {error}")
    else:
        print("No microphone library available.")

    return names


def get_default_input_device():
    if sd is None:
        return None

    try:
        return sd.default.device[0]
    except Exception:
        return None


def set_microphone(index: Optional[int]):
    global MIC_INDEX
    MIC_INDEX = index
    log(f"Microphone index set to {MIC_INDEX}")


# =========================================================
# AUDIO MATH
# =========================================================
def rms_level(audio_block) -> float:
    if np is None:
        return 0.0

    if audio_block is None:
        return 0.0

    try:
        data = np.asarray(audio_block, dtype=np.float32)

        if data.size == 0:
            return 0.0

        return float(np.sqrt(np.mean(np.square(data))))
    except Exception:
        return 0.0


def clamp_audio(audio):
    if np is None:
        return audio

    return np.clip(audio, -1.0, 1.0)


# =========================================================
# AUDIO FILE WRITER
# =========================================================
def write_wav(audio_data, sample_rate: int) -> Optional[str]:
    """
    Writes float32 audio to a temporary WAV file.
    """
    if np is None:
        log("numpy is not installed.")
        return None

    try:
        audio_data = clamp_audio(audio_data)
        pcm = (audio_data * 32767).astype(np.int16)

        temp_file = tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False
        )

        temp_path = temp_file.name
        temp_file.close()

        with wave.open(temp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())

        if VOICE_CONFIG["save_debug_audio"]:
            debug_dir = ensure_debug_dir()
            debug_file = debug_dir / f"voice_{int(time.time())}.wav"
            with wave.open(str(debug_file), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm.tobytes())

        return temp_path

    except Exception as error:
        log(f"Failed to write wav: {error}")
        return None


# =========================================================
# SMART AUDIO RECORDER
# =========================================================
def calibrate_noise(stream, sample_rate: int, block_size: int) -> float:
    """
    Measures room noise and creates adaptive threshold.
    """
    if np is None:
        return VOICE_CONFIG["min_voice_rms"]

    levels = []
    end_time = now() + VOICE_CONFIG["ambient_duration"]

    log("Calibrating microphone noise...")

    while now() < end_time:
        try:
            block, _ = stream.read(block_size)
            levels.append(rms_level(block))
        except Exception:
            break

    if not levels:
        threshold = VOICE_CONFIG["min_voice_rms"]
    else:
        noise_floor = float(np.median(levels))
        threshold = noise_floor * VOICE_CONFIG["threshold_multiplier"]
        threshold = max(threshold, VOICE_CONFIG["min_voice_rms"])
        threshold = min(threshold, VOICE_CONFIG["max_voice_rms"])

    log(f"Voice threshold: {threshold:.5f}")

    return threshold


def record_until_silence() -> Optional[str]:
    """
    Records only when voice is detected.
    Stops after silence.

    This gives Himora more natural background listening:
    - Waits for speech
    - Records phrase
    - Stops after silence
    - Returns WAV path
    """
    if sd is None or np is None:
        log("sounddevice/numpy not available.")
        return None

    sample_rate = int(VOICE_CONFIG["sample_rate"])
    channels = int(VOICE_CONFIG["channels"])
    block_size = int(sample_rate * VOICE_CONFIG["block_ms"] / 1000)

    timeout = float(VOICE_CONFIG["timeout"])
    max_duration = float(VOICE_CONFIG["phrase_time_limit"])
    silence_duration = float(VOICE_CONFIG["silence_duration"])
    min_record_seconds = float(VOICE_CONFIG["min_record_seconds"])

    chunks = []
    pre_buffer = []

    speech_started = False
    speech_start_time = None
    last_voice_time = None
    listen_start_time = now()

    device = MIC_INDEX

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            blocksize=block_size,
            device=device,
        ) as stream:

            threshold = calibrate_noise(
                stream=stream,
                sample_rate=sample_rate,
                block_size=block_size,
            )

            log("Listening...")

            while True:
                current_time = now()

                # Timeout before speech starts
                if not speech_started and current_time - listen_start_time > timeout:
                    log("Timeout waiting for speech.")
                    return None

                # Max phrase duration
                if speech_started and speech_start_time:
                    if current_time - speech_start_time > max_duration:
                        log("Phrase time limit reached.")
                        break

                block, _ = stream.read(block_size)
                level = rms_level(block)

                # Keep small pre-buffer so first syllable is not cut
                pre_buffer.append(block.copy())

                max_pre_chunks = int(0.35 / (VOICE_CONFIG["block_ms"] / 1000))
                if len(pre_buffer) > max_pre_chunks:
                    pre_buffer.pop(0)

                if not speech_started:
                    if level >= threshold:
                        speech_started = True
                        speech_start_time = current_time
                        last_voice_time = current_time

                        chunks.extend(pre_buffer)
                        chunks.append(block.copy())

                        log("Speech detected.")
                    continue

                chunks.append(block.copy())

                # Voice continues
                if level >= threshold * 0.72:
                    last_voice_time = current_time

                # Silence after voice
                if last_voice_time and current_time - last_voice_time > silence_duration:
                    recorded_for = current_time - speech_start_time

                    if recorded_for >= min_record_seconds:
                        log("Speech ended.")
                        break

        if not chunks:
            return None

        audio = np.concatenate(chunks, axis=0)

        if audio.ndim > 1:
            audio = audio[:, 0]

        return write_wav(audio, sample_rate)

    except Exception as error:
        log(f"Recording error: {error}")
        return None


# =========================================================
# TRANSCRIPTION ENGINES
# =========================================================
def transcribe_with_openai(audio_path: str) -> str:
    """
    Primary transcription engine.
    Best for multilingual and noisy voice commands.
    """
    if client is None:
        return ""

    audio_path = safe_text(audio_path)

    if not audio_path or not Path(audio_path).exists():
        return ""

    models_to_try = [
        VOICE_CONFIG["openai_model"],
        VOICE_CONFIG["openai_fallback_model"],
    ]

    for model in models_to_try:
        try:
            log(f"Transcribing with OpenAI model: {model}")

            with open(audio_path, "rb") as audio_file:
                result = client.audio.transcriptions.create(
                    model=model,
                    file=audio_file,
                )

            if isinstance(result, str):
                return smart_clean_transcript(result)

            text = getattr(result, "text", "")

            if text:
                return smart_clean_transcript(text)

        except Exception as error:
            log(f"OpenAI transcription failed with {model}: {error}")

    return ""


def transcribe_with_google(audio_path: str) -> str:
    """
    Fallback transcription.
    Uses system flac if available.
    """
    if sr is None:
        return ""

    audio_path = safe_text(audio_path)

    if not audio_path or not Path(audio_path).exists():
        return ""

    try:
        recognizer = sr.Recognizer()

        with sr.AudioFile(audio_path) as source:
            audio = recognizer.record(source)

        text = recognizer.recognize_google(
            audio,
            language="en-IN",
        )

        return smart_clean_transcript(text)

    except Exception as error:
        log(f"Google fallback transcription failed: {error}")
        return ""


def transcribe_audio_file(audio_path: str) -> str:
    engine = normalize(VOICE_CONFIG.get("engine", "auto"))

    if engine == "openai":
        return transcribe_with_openai(audio_path)

    if engine == "google":
        return transcribe_with_google(audio_path)

    # auto
    text = transcribe_with_openai(audio_path)

    if text:
        return text

    return transcribe_with_google(audio_path)


# =========================================================
# TRANSCRIPT CLEANING / SMART CORRECTION
# =========================================================
MISHEARD_COMMANDS = {
    r"\bwot\s*app\b": "whatsapp",
    r"\bwhat\s*app\b": "whatsapp",
    r"\bwhats\s*up\b": "whatsapp",
    r"\bwats\s*app\b": "whatsapp",
    r"\bwhats\s*app\b": "whatsapp",
    r"\bwhat's\s*app\b": "whatsapp",
    r"\byou\s*tube\b": "youtube",
    r"\bu\s*tube\b": "youtube",
    r"\byt\b": "youtube",
    r"\bvs\s*code\b": "vscode",
    r"\bvisual\s*studio\s*code\b": "vscode",
    r"\bchrome\b": "chrome",
    r"\bgoogal\b": "google",
    r"\bfaverite\b": "favorite",
    r"\bfavourite\b": "favorite",
    r"\bcolour\b": "color",
}


def smart_clean_transcript(text: str) -> str:
    text = safe_text(text)

    if not text:
        return ""

    text = re.sub(r"\s+", " ", text).strip()

    # Remove accidental repeated assistant name from start
    text = re.sub(
        r"^(hey\s+himora|hello\s+himora|hi\s+himora|himora)[, ]+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    for pattern, replacement in MISHEARD_COMMANDS.items():
        text = re.sub(
            pattern,
            replacement,
            text,
            flags=re.IGNORECASE,
        )

    # Clean common punctuation around commands
    text = text.strip(" .,!?:;")

    return text


def looks_unclear(text: str) -> bool:
    text = normalize(text)

    if not text:
        return True

    filler = {
        "um",
        "uh",
        "hmm",
        "huh",
        "okay",
        "ok",
        "yeah",
        "yes",
    }

    if text in filler:
        return True

    if len(text) <= 1:
        return True

    return False


# =========================================================
# MAIN LISTEN FUNCTION
# =========================================================
def listen() -> str:
    """
    Main function used by main.py.

    It:
    - records one spoken command
    - transcribes it
    - cleans common mistakes
    - returns text

    If it cannot understand, it returns "".
    main.py background loop will keep listening.
    """
    attempts = int(VOICE_CONFIG["retry_attempts"])

    for attempt in range(attempts):
        try:
            log(f"Listening attempt {attempt + 1}/{attempts}")

            audio_path = record_until_silence()

            if not audio_path:
                return ""

            try:
                text = transcribe_audio_file(audio_path)
            finally:
                try:
                    os.remove(audio_path)
                except Exception:
                    pass

            text = smart_clean_transcript(text)

            if text and not looks_unclear(text):
                log(f"Heard: {text}")
                return text

            log("Could not understand clearly.")
            return ""

        except Exception as error:
            log(f"Listen error: {error}")
            time.sleep(0.3)

    return ""


# =========================================================
# WAKE WORD SUPPORT
# =========================================================
def contains_wake_word(text: str) -> bool:
    text = normalize(text)

    return any(word in text for word in WAKE_WORDS)


def remove_wake_word(text: str) -> str:
    original = safe_text(text)
    low = normalize(original)

    for word in WAKE_WORDS:
        if low.startswith(word):
            return original[len(word):].strip(" ,.-")

    return original


def wait_for_wake_word() -> bool:
    log("Waiting for wake word...")

    while True:
        text = listen()

        if not text:
            continue

        if contains_wake_word(text):
            log("Wake word detected.")
            return True


# =========================================================
# CONTINUOUS LISTENING
# =========================================================
def continuous_listen(
    callback: Callable[[str], None],
    wake_word_required: bool = False,
    stop_check: Optional[Callable[[], bool]] = None,
):
    """
    Simple continuous mode.

    main.py currently uses its own QThread loop,
    but this remains available for future background use.
    """
    log("Continuous listening started.")

    while True:
        try:
            if stop_check and stop_check():
                log("Continuous listening stopped by stop_check.")
                break

            text = listen()

            if not text:
                continue

            low = normalize(text)

            if low in STOP_WORDS:
                log("Stop voice command detected.")
                break

            if wake_word_required:
                if not contains_wake_word(text):
                    continue

                text = remove_wake_word(text)

            if text:
                callback(text)

        except KeyboardInterrupt:
            log("Continuous listening stopped.")
            break

        except Exception as error:
            log(f"Continuous listening error: {error}")
            time.sleep(0.5)


# =========================================================
# BACKGROUND VOICE ENGINE
# =========================================================
class BackgroundVoiceEngine:
    """
    Thread-based background listener.
    Kept for compatibility with older versions.

    main.py now uses VoiceLoopWorker, but this class is useful
    if you want to run voice.py independently.
    """

    def __init__(
        self,
        callback: Callable[[str], None],
        wake_word_required: bool = False,
    ):
        self.callback = callback
        self.wake_word_required = wake_word_required
        self.running = False
        self.paused = False
        self.thread = None
        self.last_text = ""
        self.last_time = 0.0

    def _run(self):
        log("Background listening thread started.")

        while self.running:
            try:
                if self.paused:
                    time.sleep(0.2)
                    continue

                text = listen()

                if not text:
                    continue

                if self.wake_word_required:
                    if not contains_wake_word(text):
                        continue

                    text = remove_wake_word(text)

                if not text:
                    continue

                current_time = now()

                if text == self.last_text and current_time - self.last_time < 1.5:
                    continue

                self.last_text = text
                self.last_time = current_time

                self.callback(text)

            except Exception as error:
                log(f"Background voice error: {error}")
                time.sleep(0.5)

        log("Background listening thread stopped.")

    def start(self):
        if self.running:
            return

        self.running = True
        self.paused = False

        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
        )

        self.thread.start()

        log("Background listening started.")

    def stop(self):
        self.running = False
        self.paused = False
        log("Background listening stopping...")

    def pause(self):
        self.paused = True
        log("Background listening paused.")

    def resume(self):
        self.paused = False
        log("Background listening resumed.")


# =========================================================
# HEALTH CHECK
# =========================================================
def health_check() -> bool:
    print("=" * 50)
    print("HIMORA VOICE ENGINE HEALTH CHECK")
    print("=" * 50)

    ok = True

    if np is None:
        print("❌ numpy missing")
        ok = False
    else:
        print("✅ numpy available")

    if sd is None:
        print("❌ sounddevice missing")
        ok = False
    else:
        print("✅ sounddevice available")

    if client is None:
        print("⚠️ OpenAI client not ready")
        print("   Check OPENAI_API_KEY in .env")
    else:
        print("✅ OpenAI transcription ready")

    if sr is None:
        print("⚠️ SpeechRecognition fallback unavailable")
    else:
        print("✅ SpeechRecognition fallback available")

    try:
        microphones = list_microphones()
        if microphones:
            print(f"✅ microphones found: {len(microphones)}")
        else:
            print("❌ no microphone found")
            ok = False
    except Exception as error:
        print(f"❌ microphone check failed: {error}")
        ok = False

    print("=" * 50)

    return ok


def mic_test():
    print("=" * 50)
    print("HIMORA MIC TEST")
    print("Speak after you see Listening...")
    print("=" * 50)

    text = listen()

    if text:
        print(f"✅ Himora heard: {text}")
    else:
        print("❌ Himora could not understand clearly.")


# =========================================================
# DEBUG MODE
# =========================================================
if __name__ == "__main__":
    if health_check():
        while True:
            try:
                print("\nSpeak now. Press Ctrl+C to stop.")
                heard = listen()

                if heard:
                    print("You said:", heard)
                else:
                    print("No clear speech detected.")

            except KeyboardInterrupt:
                print("\nVoice test stopped.")
                break