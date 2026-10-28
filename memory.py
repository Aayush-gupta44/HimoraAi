import os
import json
import time
from pathlib import Path

# =========================================================
# PATHS
# =========================================================
BASE_DIR = Path(__file__).resolve().parent

MEMORY_DIR = BASE_DIR / "memory_data"
MEMORY_DIR.mkdir(exist_ok=True)

SHORT_MEMORY_FILE = MEMORY_DIR / "short_memory.json"
LONG_MEMORY_FILE = MEMORY_DIR / "long_memory.json"
PROFILE_FILE = MEMORY_DIR / "profile.json"

# =========================================================
# CONFIG
# =========================================================
SHORT_MEMORY_LIMIT = 30


# =========================================================
# LOGGER
# =========================================================
def log(message):
    print(f"[MEMORY] {message}")


# =========================================================
# SAFE LOAD
# =========================================================
def safe_load(file_path):
    if not file_path.exists():
        return []

    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except:
        return []


# =========================================================
# SAFE SAVE
# =========================================================
def safe_save(file_path, data):
    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        log(f"Save error: {e}")


# =========================================================
# SHORT TERM MEMORY
# =========================================================
def load_short_memory():
    return safe_load(SHORT_MEMORY_FILE)


def save_short_memory(role, content):
    memory = load_short_memory()

    memory.append({
        "role": role,
        "content": content,
        "timestamp": time.time()
    })

    if len(memory) > SHORT_MEMORY_LIMIT:
        memory.pop(0)

    safe_save(SHORT_MEMORY_FILE, memory)


def get_recent_context(limit=10):
    memory = load_short_memory()

    recent = memory[-limit:]

    context = ""

    for msg in recent:
        context += f"{msg['role']}: {msg['content']}\n"

    return context


# =========================================================
# LONG TERM MEMORY
# =========================================================
def load_long_memory():
    data = safe_load(LONG_MEMORY_FILE)

    if isinstance(data, list):
        return data

    return []


def save_long_memory(key, value):
    memory = load_long_memory()

    found = False

    for item in memory:
        if item["key"] == key:
            item["value"] = value
            item["updated"] = time.time()
            found = True

    if not found:
        memory.append({
            "key": key,
            "value": value,
            "created": time.time()
        })

    safe_save(LONG_MEMORY_FILE, memory)


def get_long_memory(key):
    memory = load_long_memory()

    for item in memory:
        if item["key"] == key:
            return item["value"]

    return None


# =========================================================
# USER PROFILE MEMORY
# =========================================================
def load_profile():
    if not PROFILE_FILE.exists():
        return {}

    try:
        with open(PROFILE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}


def save_profile_field(field, value):
    profile = load_profile()

    profile[field] = value

    safe_save(PROFILE_FILE, profile)


def get_profile_field(field):
    profile = load_profile()

    return profile.get(field)


# =========================================================
# LEARNING ENGINE
# =========================================================
def learn_from_message(user_message):
    text = user_message.lower()

    if "dad means" in text:
        name = text.replace("dad means", "").strip()

        save_long_memory("dad", name)

        return f"Learned that dad means {name}"

    if "mom means" in text:
        name = text.replace("mom means", "").strip()

        save_long_memory("mom", name)

        return f"Learned that mom means {name}"

    if "my favorite song is" in text:
        song = text.replace("my favorite song is", "").strip()

        save_profile_field("favorite_song", song)

        return f"Learned favorite song {song}"

    if "my favorite app is" in text:
        app = text.replace("my favorite app is", "").strip()

        save_profile_field("favorite_app", app)

        return f"Learned favorite app {app}"

    return None


# =========================================================
# MEMORY SEARCH
# =========================================================
def search_memory(query):
    query = query.lower()

    short_memory = load_short_memory()
    results = []

    for msg in short_memory:
        if query in msg["content"].lower():
            results.append(msg)

    return results


# =========================================================
# RESOLVE CONTACT
# =========================================================
def resolve_contact(name):
    stored = get_long_memory(name.lower())

    if stored:
        return stored

    return name


# =========================================================
# CONTEXT BUILDER FOR GPT
# =========================================================
def build_full_context():
    recent = get_recent_context(8)

    profile = load_profile()

    long_memory = load_long_memory()

    profile_text = "\n".join(
        [f"{k}: {v}" for k, v in profile.items()]
    )

    long_text = ""

    for item in long_memory:
        long_text += f"{item['key']} = {item['value']}\n"

    final_context = f"""
RECENT CONVERSATION:
{recent}

USER PROFILE:
{profile_text}

LONG TERM MEMORY:
{long_text}
"""

    return final_context.strip()


# =========================================================
# CLEAR MEMORY
# =========================================================
def clear_short_memory():
    safe_save(SHORT_MEMORY_FILE, [])


def clear_all_memory():
    safe_save(SHORT_MEMORY_FILE, [])
    safe_save(LONG_MEMORY_FILE, [])
    safe_save(PROFILE_FILE, {})


# =========================================================
# DEBUG MODE
# =========================================================
if __name__ == "__main__":
    save_short_memory("user", "Hello Himora")
    save_short_memory("assistant", "Hello Aayu")

    save_long_memory("dad", "Om Gupta")

    print(build_full_context())