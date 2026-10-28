from context import build_context_summary
from memory import build_full_context
import os
import json
import time
from typing import Dict, Any
from dotenv import load_dotenv
from openai import OpenAI

# =========================================================
# LOAD ENV
# =========================================================
load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# =========================================================
# SYSTEM CORE PROMPT
# =========================================================
SYSTEM_PROMPT = """
You are Himora v3.

You are an advanced AI operating system assistant.

Your job:
1. Understand user intent deeply.
2. Convert requests into structured JSON.
3. Break complex tasks into steps.
4. Use memory context and device context.
5. Be context-aware.

Distinguish between:
- chat
- desktop actions
- browser actions
- app actions
- youtube actions
- whatsapp actions
- typing actions
- system actions
- search actions

STRICT RULES:

Return ONLY valid JSON.

Schema:

{
    "type": "single" or "multi",
    "confidence": 0.0-1.0,
    "intent": "...",
    "steps": [
        {
            "action": "...",
            "params": {}
        }
    ],
    "response": "optional"
}

Important:

If user asks informational question:
ALWAYS use intent = chat.

If user says:
"write about stock market"
This means CHAT.

NOT type_text.

Only use type_text when user explicitly wants typing somewhere.

Use DEVICE CONTEXT to understand:
- active app
- active window
- last actions

Use MEMORY CONTEXT to understand:
- previous conversation
- stored contact names
- user preferences
"""

# =========================================================
# FAST RUNTIME MEMORY
# =========================================================
conversation_memory = []

# =========================================================
# VALID ACTIONS
# =========================================================
VALID_ACTIONS = {
    "open_app",
    "open_website",
    "youtube_search",
    "youtube_play_first",
    "search_contact",
    "send_message",
    "type_text",
    "browser_search",
    "close_app",
    "system_volume",
    "system_brightness",
    "chat"
    "analyze_screen",
    "analyze_graph",
    "analyze_ui"
}


# =========================================================
# MEMORY FUNCTIONS
# =========================================================
def save_memory(role: str, content: str):
    conversation_memory.append({
        "role": role,
        "content": content,
        "timestamp": time.time()
    })

    if len(conversation_memory) > 20:
        conversation_memory.pop(0)


def build_runtime_context():
    history = ""

    for msg in conversation_memory:
        history += f"{msg['role']}: {msg['content']}\n"

    return history


# =========================================================
# JSON PARSER
# =========================================================
def safe_parse_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)

    except Exception:
        return {
            "type": "single",
            "confidence": 0.40,
            "intent": "chat",
            "steps": [],
            "response": text
        }


# =========================================================
# VALIDATOR
# =========================================================
def validate_steps(steps):
    validated = []

    for step in steps:
        action = step.get("action")

        if action in VALID_ACTIONS:
            validated.append(step)

    return validated


# =========================================================
# LOCAL FALLBACK
# =========================================================
def local_intent_fallback(prompt: str):
    prompt = prompt.lower()

    if "youtube" in prompt:
        return {
            "type": "single",
            "confidence": 0.80,
            "intent": "youtube_search",
            "steps": [
                {
                    "action": "youtube_search",
                    "params": {
                        "query": prompt.replace("youtube", "").strip()
                    }
                }
            ]
        }

    if "whatsapp" in prompt:
        return {
            "type": "single",
            "confidence": 0.80,
            "intent": "open_app",
            "steps": [
                {
                    "action": "open_app",
                    "params": {
                        "app": "whatsapp"
                    }
                }
            ]
        }

    if prompt.startswith("open "):
        app_name = prompt.replace("open ", "").strip()

        return {
            "type": "single",
            "confidence": 0.75,
            "intent": "open_app",
            "steps": [
                {
                    "action": "open_app",
                    "params": {
                        "app": app_name
                    }
                }
            ]
        }

    return {
        "type": "single",
        "confidence": 0.50,
        "intent": "chat",
        "steps": [],
        "response": "Can you clarify that?"
    }


# =========================================================
# GPT THINKING
# =========================================================
def gpt_reason(prompt: str):
    runtime_context = build_runtime_context()

    # NEW MEMORY + DEVICE CONTEXT
    memory_context = build_full_context()
    device_context = build_context_summary()

    context = f"""
MEMORY CONTEXT:
{memory_context}

DEVICE CONTEXT:
{device_context}

LIVE RUNTIME CHAT:
{runtime_context}
"""

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "system",
            "content": context
        },
        {
            "role": "user",
            "content": prompt
        }
    ]

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.3
    )

    output = response.choices[0].message.content.strip()

    return output


# =========================================================
# MAIN THINK ENGINE
# =========================================================
def think(prompt: str):
    save_memory("user", prompt)

    try:
        raw = gpt_reason(prompt)

        parsed = safe_parse_json(raw)

        if "steps" in parsed:
            parsed["steps"] = validate_steps(
                parsed["steps"]
            )

        if parsed.get("confidence", 0) < 0.55:
            parsed = local_intent_fallback(prompt)

        if parsed.get("response"):
            save_memory(
                "assistant",
                parsed["response"]
            )

        return parsed

    except Exception as e:
        print("[BRAIN ERROR]", e)

        fallback = local_intent_fallback(prompt)

        return fallback


# =========================================================
# TASK EXPLAINER
# =========================================================
def explain_plan(task):
    if not task:
        return "No task."

    intent = task.get("intent")
    confidence = task.get("confidence")
    steps = task.get("steps", [])

    summary = f"""
Intent: {intent}
Confidence: {confidence}
Steps:
"""

    for i, step in enumerate(steps):
        summary += (
            f"{i+1}. "
            f"{step['action']} -> "
            f"{step.get('params', {})}\n"
        )

    return summary


# =========================================================
# DEBUG MODE
# =========================================================
if __name__ == "__main__":
    while True:
        user_input = input("You: ")

        task = think(user_input)

        print("\nTASK:")
        print(
            json.dumps(
                task,
                indent=4
            )
        )

        print("\nPLAN:")
        print(
            explain_plan(task)
        )