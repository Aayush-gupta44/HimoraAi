import json
import os
import time


REFLECTION_FILE = "reflection_log.json"


# =========================================================
# INIT FILE
# =========================================================
def init_reflection():
    if not os.path.exists(REFLECTION_FILE):
        with open(REFLECTION_FILE, "w") as f:
            json.dump([], f)


# =========================================================
# LOAD LOGS
# =========================================================
def load_logs():
    init_reflection()

    with open(REFLECTION_FILE, "r") as f:
        return json.load(f)


# =========================================================
# SAVE LOGS
# =========================================================
def save_logs(logs):
    with open(REFLECTION_FILE, "w") as f:
        json.dump(logs, f, indent=4)


# =========================================================
# STORE RESULT
# =========================================================
def store_reflection(action, success, details=""):
    logs = load_logs()

    logs.append({
        "action": action,
        "success": success,
        "details": details,
        "timestamp": time.time()
    })

    if len(logs) > 200:
        logs.pop(0)

    save_logs(logs)


# =========================================================
# GET FAILURE COUNT
# =========================================================
def failure_count(action):
    logs = load_logs()

    count = 0

    for log in logs:
        if log["action"] == action and not log["success"]:
            count += 1

    return count


# =========================================================
# GET SUCCESS COUNT
# =========================================================
def success_count(action):
    logs = load_logs()

    count = 0

    for log in logs:
        if log["action"] == action and log["success"]:
            count += 1

    return count


# =========================================================
# BEST STRATEGY
# =========================================================
def get_action_confidence(action):
    success = success_count(action)
    failure = failure_count(action)

    total = success + failure

    if total == 0:
        return 0.5

    return success / total


# =========================================================
# SUGGEST IMPROVEMENT
# =========================================================
def suggest_improvement(action):
    failures = failure_count(action)

    if failures >= 3:
        return f"Action '{action}' has failed multiple times. Try alternate execution."

    return None


# =========================================================
# ACTION HEALTH
# =========================================================
def action_health_report():
    logs = load_logs()

    summary = {}

    for log in logs:
        action = log["action"]

        if action not in summary:
            summary[action] = {
                "success": 0,
                "failure": 0
            }

        if log["success"]:
            summary[action]["success"] += 1
        else:
            summary[action]["failure"] += 1

    return summary


# =========================================================
# DEBUG
# =========================================================
if __name__ == "__main__":
    print(action_health_report())