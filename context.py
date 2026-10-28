import subprocess
import webbrowser
import time


# =========================================================
# GLOBAL CONTEXT STATE
# =========================================================
context_state = {
    "active_app": None,
    "active_window": None,
    "last_website": None,
    "last_search": None,
    "last_contact": None,
    "last_action": None,
    "last_response": None
}


# =========================================================
# LOGGER
# =========================================================
def log(message):
    print(f"[CONTEXT] {message}")


# =========================================================
# GET ACTIVE APP (MAC)
# =========================================================
def get_active_app():
    try:
        script = '''
        tell application "System Events"
            name of first application process whose frontmost is true
        end tell
        '''

        result = subprocess.check_output(
            ["osascript", "-e", script]
        ).decode().strip()

        context_state["active_app"] = result.lower()

        return result

    except Exception as e:
        log(f"Active app error: {e}")
        return None


# =========================================================
# GET ACTIVE WINDOW TITLE (MAC)
# =========================================================
def get_active_window():
    try:
        script = '''
        tell application "System Events"
            tell (first application process whose frontmost is true)
                get name of front window
            end tell
        end tell
        '''

        result = subprocess.check_output(
            ["osascript", "-e", script]
        ).decode().strip()

        context_state["active_window"] = result

        return result

    except Exception as e:
        log(f"Window error: {e}")
        return None


# =========================================================
# UPDATE CONTEXT
# =========================================================
def update_context():
    app = get_active_app()
    window = get_active_window()

    context_state["active_app"] = app
    context_state["active_window"] = window

    return context_state


# =========================================================
# SAVE LAST WEBSITE
# =========================================================
def set_last_website(url):
    context_state["last_website"] = url


# =========================================================
# SAVE LAST SEARCH
# =========================================================
def set_last_search(query):
    context_state["last_search"] = query


# =========================================================
# SAVE LAST CONTACT
# =========================================================
def set_last_contact(name):
    context_state["last_contact"] = name


# =========================================================
# SAVE LAST ACTION
# =========================================================
def set_last_action(action):
    context_state["last_action"] = action


# =========================================================
# SAVE LAST RESPONSE
# =========================================================
def set_last_response(response):
    context_state["last_response"] = response


# =========================================================
# GET CONTEXT SUMMARY
# =========================================================
def build_context_summary():
    update_context()

    summary = f"""
ACTIVE APP: {context_state['active_app']}
ACTIVE WINDOW: {context_state['active_window']}
LAST WEBSITE: {context_state['last_website']}
LAST SEARCH: {context_state['last_search']}
LAST CONTACT: {context_state['last_contact']}
LAST ACTION: {context_state['last_action']}
LAST RESPONSE: {context_state['last_response']}
"""

    return summary.strip()


# =========================================================
# APP CHECKERS
# =========================================================
def is_whatsapp_active():
    app = get_active_app()

    if not app:
        return False

    return "whatsapp" in app.lower()


def is_browser_active():
    app = get_active_app()

    if not app:
        return False

    browsers = [
        "chrome",
        "safari",
        "firefox",
        "edge"
    ]

    for browser in browsers:
        if browser in app.lower():
            return True

    return False


# =========================================================
# CONTEXT DECISION HELPERS
# =========================================================
def can_type_here():
    app = get_active_app()

    if not app:
        return False

    allowed = [
        "whatsapp",
        "notes",
        "chrome",
        "safari",
        "terminal"
    ]

    for a in allowed:
        if a in app.lower():
            return True

    return False


# =========================================================
# CONTEXTUAL TARGET INFERENCE
# =========================================================
def infer_target():
    if context_state["last_contact"]:
        return context_state["last_contact"]

    if context_state["active_window"]:
        return context_state["active_window"]

    return None


# =========================================================
# DEBUG MODE
# =========================================================
if __name__ == "__main__":
    print(build_context_summary())