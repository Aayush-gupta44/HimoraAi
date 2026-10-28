"""
Himora Advanced Gmail Agent
---------------------------

This file gives Himora Gmail-specific power.

It can:
- Open Gmail
- Compose a Gmail draft
- Parse recipient from natural command
- Generate subject and body
- Fill Gmail compose screen using Gmail compose URL
- Ask for approval before sending
- Send only after approval
- Discard pending draft state
- Store pending draft state in memory_data/gmail_pending.json

Important:
This agent does NOT send automatically.
It composes first, then asks user for approval.

Example commands this file supports through executor/router later:

- open gmail
- open gmail and compose
- compose gmail to test@gmail.com about cyber fraud
- write email to esewa about scam
- send it
- yes send it
- discard gmail draft

Dependencies:
python -m pip install pyperclip python-dotenv openai

Optional:
Gmail should already be logged in inside your browser.
"""

import os
import re
import json
import time
import webbrowser
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


# =========================================================
# OPTIONAL IMPORTS
# =========================================================
try:
    import pyautogui
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
# PATHS
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory_data"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

PENDING_FILE = MEMORY_DIR / "gmail_pending.json"


# =========================================================
# CONFIG
# =========================================================
GMAIL_BASE = "https://mail.google.com/mail/u/0/"
GMAIL_COMPOSE_URL = "https://mail.google.com/mail/u/0/?view=cm&fs=1&tf=1"

DEFAULT_BROWSER_APP = os.getenv("HIMORA_BROWSER_APP", "").strip()

GMAIL_CONFIG = {
    "wait_after_open": 2.0,
    "wait_after_compose": 3.0,
    "send_hotkeys": [
        ("command", "enter"),
        ("ctrl", "enter"),
    ],
    "model": os.getenv("HIMORA_GMAIL_MODEL", "gpt-4.1-mini"),
}


# =========================================================
# LOGGER
# =========================================================
def log(message: str):
    print(f"[GMAIL AGENT] {message}")


# =========================================================
# DATA MODEL
# =========================================================
@dataclass
class GmailDraft:
    to: str = ""
    subject: str = ""
    body: str = ""
    topic: str = ""
    source_command: str = ""
    status: str = "draft_ready"
    created_at: float = 0.0
    needs_approval: bool = True

    def is_valid(self) -> bool:
        return bool(self.to and self.subject and self.body)


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


def safe_sleep(seconds: float):
    time.sleep(seconds)


def read_json(path: Path, default: Any):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        log(f"Failed to read json: {error}")
    return default


def write_json(path: Path, data: Any):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except Exception as error:
        log(f"Failed to write json: {error}")
        return False


def paste_text(text: str) -> bool:
    text = clean_text(text)

    if not text:
        return False

    if pyperclip and pyautogui:
        pyperclip.copy(text)
        safe_sleep(0.1)
        pyautogui.hotkey("command", "v")
        return True

    if pyautogui:
        pyautogui.write(text, interval=0.01)
        return True

    return False


def open_url(url: str):
    if DEFAULT_BROWSER_APP:
        try:
            subprocess.run(
                ["open", "-a", DEFAULT_BROWSER_APP, url],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass

    webbrowser.open(url)


# =========================================================
# EMAIL PARSING
# =========================================================
EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+"
)


def extract_emails(text: str) -> List[str]:
    return EMAIL_REGEX.findall(clean_text(text))


def is_valid_email(email: str) -> bool:
    email = clean_text(email)
    return bool(EMAIL_REGEX.fullmatch(email))


def remove_email_from_text(text: str, email: str) -> str:
    return compact_spaces(clean_text(text).replace(email, " "))


def extract_recipient(command: str) -> str:
    command = clean_text(command)

    emails = extract_emails(command)

    if emails:
        return emails[0]

    return ""


def extract_topic(command: str, recipient: str = "") -> str:
    raw = compact_spaces(command)
    low = normalize(raw)

    text = raw

    if recipient:
        text = remove_email_from_text(text, recipient)

    cleanup_patterns = [
        r"^compose\s+gmail\s+",
        r"^compose\s+email\s+",
        r"^write\s+gmail\s+",
        r"^write\s+email\s+",
        r"^gmail\s+compose\s+",
        r"^open\s+gmail\s+and\s+compose\s+",
        r"^send\s+email\s+",
        r"^mail\s+",
        r"\bto\s*$",
    ]

    for pattern in cleanup_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

    # Strong “about X” extraction
    about_match = re.search(
        r"\babout\s+(.+)$",
        text,
        re.IGNORECASE,
    )

    if about_match:
        topic = about_match.group(1).strip(" .,!?:;")
        return topic

    # “regarding X”
    regarding_match = re.search(
        r"\bregarding\s+(.+)$",
        text,
        re.IGNORECASE,
    )

    if regarding_match:
        topic = regarding_match.group(1).strip(" .,!?:;")
        return topic

    # “on X”
    on_match = re.search(
        r"\bon\s+(.+)$",
        text,
        re.IGNORECASE,
    )

    if on_match:
        topic = on_match.group(1).strip(" .,!?:;")
        return topic

    # Remove “to someone”
    text = re.sub(
        r"\bto\s+[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = compact_spaces(text)

    return text.strip(" .,!?:;")


# =========================================================
# SUBJECT GENERATION
# =========================================================
def infer_subject(topic: str, command: str = "") -> str:
    topic_low = normalize(topic)
    command_low = normalize(command)

    if "cyber fraud" in topic_low or "online fraud" in topic_low:
        return "Request for Assistance Regarding Cyber Fraud"

    if "scam" in topic_low or "fraud" in topic_low:
        return "Request for Assistance Regarding Fraud Case"

    if "payment" in topic_low and ("issue" in topic_low or "problem" in topic_low):
        return "Request for Assistance Regarding Payment Issue"

    if "esewa" in topic_low or "e-sewa" in topic_low:
        return "Request for Support Regarding eSewa Transaction Issue"

    if "admission" in topic_low:
        return "Admission Inquiry"

    if "scholarship" in topic_low:
        return "Scholarship Inquiry"

    if "collaboration" in topic_low or "partnership" in topic_low:
        return "Request for Collaboration"

    if "complaint" in topic_low:
        return "Formal Complaint"

    if topic:
        cleaned = compact_spaces(topic)
        cleaned = cleaned[:70].strip(" .,!?:;")
        return cleaned[:1].upper() + cleaned[1:]

    if command_low:
        return "Regarding Your Assistance"

    return "Inquiry"


# =========================================================
# BODY GENERATION
# =========================================================
def fallback_body(topic: str, command: str = "") -> str:
    topic = clean_text(topic) or clean_text(command) or "the matter"

    low = normalize(topic + " " + command)

    if "cyber fraud" in low or "scam" in low or "fraud" in low:
        return (
            "Dear Sir/Madam,\n\n"
            "I am writing to request your assistance regarding a possible cyber fraud/scam incident. "
            "I believe I may have been misled or defrauded, and I would like your team to kindly review the matter.\n\n"
            "I can provide the relevant account details, transaction information, screenshots, and chat records for verification. "
            "Please look into this issue and guide me on the next steps required to report or resolve the case.\n\n"
            "I would be grateful for your urgent support and response.\n\n"
            "Sincerely,\n"
            "Aayush Gupta"
        )

    return (
        "Dear Sir/Madam,\n\n"
        f"I am writing to request your assistance regarding {topic}. "
        "Please kindly review this matter and let me know the next steps.\n\n"
        "I would appreciate your support and response.\n\n"
        "Sincerely,\n"
        "Aayush Gupta"
    )


def generate_body_with_openai(topic: str, command: str = "") -> str:
    if client is None:
        return fallback_body(topic, command)

    topic = clean_text(topic)
    command = clean_text(command)

    system_prompt = """
You are Himora's Gmail writing agent.

Write a clear, polite, formal email body.

Rules:
- Do not include subject.
- Do not include recipient email.
- Use simple professional English.
- Keep it realistic.
- If the user mentions scam/fraud/cyber fraud, ask the receiver to review account details, transaction details, screenshots, and chats.
- Do not claim facts that the user did not provide.
- End with:
Sincerely,
Aayush Gupta
"""

    user_prompt = f"""
User command:
{command}

Email topic:
{topic}

Write the email body only.
"""

    try:
        response = client.chat.completions.create(
            model=GMAIL_CONFIG["model"],
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            temperature=0.35,
        )

        body = response.choices[0].message.content.strip()

        if body:
            return body

    except Exception as error:
        log(f"OpenAI body generation failed: {error}")

    return fallback_body(topic, command)


# =========================================================
# PENDING DRAFT STATE
# =========================================================
def save_pending_draft(draft: GmailDraft):
    draft.created_at = draft.created_at or time.time()
    write_json(PENDING_FILE, asdict(draft))


def load_pending_draft() -> Optional[GmailDraft]:
    data = read_json(PENDING_FILE, None)

    if not data:
        return None

    try:
        return GmailDraft(**data)
    except Exception:
        return None


def clear_pending_draft():
    try:
        if PENDING_FILE.exists():
            PENDING_FILE.unlink()
    except Exception:
        pass


def has_pending_draft() -> bool:
    draft = load_pending_draft()
    return bool(draft and draft.is_valid())


# =========================================================
# GMAIL OPEN / COMPOSE URL
# =========================================================
def build_compose_url(
    to: str = "",
    subject: str = "",
    body: str = "",
) -> str:
    url = GMAIL_COMPOSE_URL

    params = []

    if to:
        params.append(f"to={quote_plus(to)}")

    if subject:
        params.append(f"su={quote_plus(subject)}")

    if body:
        params.append(f"body={quote_plus(body)}")

    if params:
        url = url + "&" + "&".join(params)

    return url


def open_gmail() -> str:
    log("Opening Gmail")
    open_url(GMAIL_BASE)
    safe_sleep(GMAIL_CONFIG["wait_after_open"])
    return "Opening Gmail."


def open_gmail_compose_empty() -> str:
    log("Opening Gmail compose")
    open_url(GMAIL_COMPOSE_URL)
    safe_sleep(GMAIL_CONFIG["wait_after_compose"])
    return "Opening Gmail compose."


def open_gmail_compose_with_draft(draft: GmailDraft) -> str:
    if not draft:
        return "No draft provided."

    url = build_compose_url(
        to=draft.to,
        subject=draft.subject,
        body=draft.body,
    )

    log(f"Opening Gmail compose draft for {draft.to}")

    open_url(url)
    safe_sleep(GMAIL_CONFIG["wait_after_compose"])

    save_pending_draft(draft)

    return (
        "I composed the Gmail draft. "
        "Please review it. Should I send it?"
    )


# =========================================================
# GMAIL COMPOSE MAIN
# =========================================================
def compose_email(
    to: str = "",
    subject: str = "",
    body: str = "",
    topic: str = "",
    source_command: str = "",
) -> str:
    to = clean_text(to)
    subject = clean_text(subject)
    body = clean_text(body)
    topic = clean_text(topic)
    source_command = clean_text(source_command)

    if not to:
        return (
            "Who should I send the email to? "
            "Please give me the recipient email address."
        )

    if not is_valid_email(to):
        return f"The email address {to} does not look valid."

    if not subject:
        subject = infer_subject(topic, source_command)

    if not body:
        body = generate_body_with_openai(topic, source_command)

    draft = GmailDraft(
        to=to,
        subject=subject,
        body=body,
        topic=topic,
        source_command=source_command,
        status="draft_composed",
        created_at=time.time(),
        needs_approval=True,
    )

    return open_gmail_compose_with_draft(draft)


def compose_from_command(command: str) -> str:
    """
    Natural language command parser.

    Examples:
    - compose gmail to dash8439@gmail.com about cyber fraud
    - write email to test@gmail.com regarding payment issue
    - send email to abc@gmail.com about admission inquiry
    """
    command = compact_spaces(command)

    if not command:
        return "What email should I compose?"

    recipient = extract_recipient(command)

    if not recipient:
        open_gmail_compose_empty()
        return (
            "I opened Gmail compose. "
            "Please provide the recipient email address and topic."
        )

    topic = extract_topic(command, recipient)

    if not topic:
        topic = "your requested matter"

    subject = infer_subject(topic, command)
    body = generate_body_with_openai(topic, command)

    return compose_email(
        to=recipient,
        subject=subject,
        body=body,
        topic=topic,
        source_command=command,
    )


# =========================================================
# SEND / APPROVAL
# =========================================================
def is_send_confirmation(text: str) -> bool:
    low = normalize(text)

    confirmations = [
        "send it",
        "yes send it",
        "send the email",
        "yes send",
        "approve send",
        "you can send",
        "send now",
        "yes",
    ]

    return low in confirmations


def is_discard_command(text: str) -> bool:
    low = normalize(text)

    discards = [
        "discard gmail draft",
        "discard email",
        "cancel email",
        "delete email draft",
        "do not send",
        "dont send",
        "don't send",
        "cancel it",
    ]

    return low in discards


def send_pending_email() -> str:
    """
    Sends the currently open Gmail compose window.

    This should ONLY be called after user approval.

    It tries Gmail's send shortcut.
    Gmail commonly supports Command+Enter / Ctrl+Enter for send.
    """
    draft = load_pending_draft()

    if not draft or not draft.is_valid():
        return "There is no pending Gmail draft to send."

    if pyautogui is None:
        return "I cannot send because pyautogui is not available."

    log("Sending pending Gmail draft after approval")

    try:
        # Make sure browser/Gmail is active enough.
        # Then try send hotkeys.
        for keys in GMAIL_CONFIG["send_hotkeys"]:
            pyautogui.hotkey(*keys)
            safe_sleep(0.8)

        draft.status = "sent_attempted"
        draft.needs_approval = False
        save_pending_draft(draft)

        clear_pending_draft()

        return "I sent the Gmail draft."

    except Exception as error:
        log(f"Failed to send Gmail draft: {error}")
        return f"I could not send the Gmail draft: {error}"


def handle_gmail_approval_command(text: str) -> Optional[str]:
    """
    Main/router/executor can call this before normal processing.

    If user says:
    - send it
    - yes send it

    and there is a pending Gmail draft,
    this sends it.
    """
    if is_discard_command(text):
        if has_pending_draft():
            clear_pending_draft()
            return "Okay, I discarded the pending Gmail draft."
        return "There is no pending Gmail draft to discard."

    if is_send_confirmation(text):
        if has_pending_draft():
            return send_pending_email()

    return None


# =========================================================
# STATUS / DEBUG
# =========================================================
def pending_draft_summary() -> str:
    draft = load_pending_draft()

    if not draft:
        return "There is no pending Gmail draft."

    return (
        "Pending Gmail draft:\n"
        f"To: {draft.to}\n"
        f"Subject: {draft.subject}\n\n"
        f"{draft.body}"
    )


def gmail_status() -> Dict[str, Any]:
    draft = load_pending_draft()

    return {
        "has_pending_draft": bool(draft and draft.is_valid()),
        "pending_file": str(PENDING_FILE),
        "openai_ready": client is not None,
        "pyautogui_ready": pyautogui is not None,
        "pyperclip_ready": pyperclip is not None,
    }


# =========================================================
# ROUTE HELPER FOR EXECUTOR
# =========================================================
def execute_gmail_action(action: str, params: Optional[Dict[str, Any]] = None) -> str:
    """
    Executor can call this function.

    Supported actions:
    - gmail_open
    - gmail_compose
    - gmail_compose_from_command
    - gmail_send_pending
    - gmail_discard_pending
    - gmail_pending_summary
    """
    params = params or {}

    action = clean_text(action)

    if action == "gmail_open":
        return open_gmail()

    if action == "gmail_compose":
        return compose_email(
            to=params.get("to", ""),
            subject=params.get("subject", ""),
            body=params.get("body", ""),
            topic=params.get("topic", ""),
            source_command=params.get("source_command", ""),
        )

    if action == "gmail_compose_from_command":
        return compose_from_command(
            params.get("command", "")
        )

    if action == "gmail_send_pending":
        return send_pending_email()

    if action == "gmail_discard_pending":
        clear_pending_draft()
        return "Discarded the pending Gmail draft."

    if action == "gmail_pending_summary":
        return pending_draft_summary()

    return f"Unknown Gmail action: {action}"


# =========================================================
# DIRECT TEST
# =========================================================
if __name__ == "__main__":
    print("=" * 60)
    print("HIMORA GMAIL AGENT TEST")
    print("=" * 60)

    print("Status:")
    print(json.dumps(gmail_status(), indent=4))

    while True:
        try:
            command = input("\nGmail command: ").strip()

            if command.lower() in ["exit", "quit"]:
                break

            approval = handle_gmail_approval_command(command)

            if approval:
                print(approval)
                continue

            if command.lower() in ["status", "draft", "pending"]:
                print(pending_draft_summary())
                continue

            print(compose_from_command(command))

        except KeyboardInterrupt:
            print("\nStopped.")
            break

        except Exception as error:
            print("Error:", error)