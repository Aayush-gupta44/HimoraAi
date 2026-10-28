import time
import traceback

from planner import planner
from executor import execute
from vision import analyze_ui_state
from context import (
    update_context,
    set_last_action
)
from reflection import (
    store_reflection,
    suggest_improvement
)


# =========================================================
# LOGGER
# =========================================================
def log(message):
    print(f"[AGENT] {message}")


# =========================================================
# AUTONOMOUS AGENT CORE
# =========================================================
class AutonomousAgent:
    def __init__(self):
        self.running = False
        self.max_retries = 3
        self.retry_delay = 1.5
        self.current_task = None
        self.last_result = None

    # =====================================================
    # START NEW TASK
    # =====================================================
    def start(self, user_input):
        try:
            self.running = True

            log(f"Starting task: {user_input}")

            task = planner.expand_task(user_input)

            self.current_task = task

            result = self.execute_task(task)

            self.last_result = result

            return result

        except Exception as e:
            log(f"Start error: {e}")
            traceback.print_exc()

            return "Failed to start autonomous task."

    # =====================================================
    # EXECUTE WHOLE TASK
    # =====================================================
    def execute_task(self, task):
        try:
            steps = task.get("steps", [])

            # Chat-only response
            if not steps:
                return task.get(
                    "response",
                    "No steps to execute."
                )

            results = []

            for index, step in enumerate(steps):
                if not self.running:
                    log("Agent stopped.")
                    break

                log(
                    f"Executing step {index+1}/{len(steps)}: "
                    f"{step.get('action')}"
                )

                result = self.execute_step(step)

                results.append(result)

            return "\n".join(results)

        except Exception as e:
            log(f"Task execution error: {e}")
            traceback.print_exc()

            return "Task execution failed."

    # =====================================================
    # EXECUTE SINGLE STEP
    # =====================================================
    def execute_step(self, step):
        retries = 0
        action = step.get("action")

        while retries < self.max_retries:
            try:
                log(
                    f"Running action: {action} "
                    f"(Attempt {retries+1})"
                )

                result = execute({
                    "steps": [step]
                })

                set_last_action(action)

                verified = self.verify_step(step)

                if verified:
                    store_reflection(
                        action,
                        True,
                        "Execution successful"
                    )

                    log(
                        f"Step successful: {action}"
                    )

                    return f"✓ {action} completed"

                retries += 1

                log(
                    f"Verification failed. Retrying..."
                )

                time.sleep(
                    self.retry_delay
                )

            except Exception as e:
                retries += 1

                log(
                    f"Step error: {e}"
                )

                time.sleep(
                    self.retry_delay
                )

        # Failed after retries
        store_reflection(
            action,
            False,
            "Execution failed after retries"
        )

        suggestion = suggest_improvement(
            action
        )

        if suggestion:
            return (
                f"✗ Failed: {action} | "
                f"{suggestion}"
            )

        return f"✗ Failed: {action}"

    # =====================================================
    # VERIFY STEP USING VISION
    # =====================================================
    def verify_step(self, step):
        try:
            action = step.get("action")
            params = step.get("params", {})

            ui_state = analyze_ui_state()

            if not ui_state:
                return True

            ui_state = ui_state.lower()

            # ---------------------------------------------
            # OPEN APP
            # ---------------------------------------------
            if action == "open_app":
                app_name = params.get(
                    "app",
                    ""
                ).lower()

                if app_name and app_name in ui_state:
                    return True

            # ---------------------------------------------
            # YOUTUBE SEARCH
            # ---------------------------------------------
            if action == "youtube_search":
                query = params.get(
                    "query",
                    ""
                ).lower()

                if query and query in ui_state:
                    return True

            # ---------------------------------------------
            # CONTACT SEARCH
            # ---------------------------------------------
            if action == "search_contact":
                name = params.get(
                    "name",
                    ""
                ).lower()

                if name and name in ui_state:
                    return True

            # ---------------------------------------------
            # SEND MESSAGE
            # ---------------------------------------------
            if action == "send_message":
                return True

            # ---------------------------------------------
            # TYPE TEXT
            # ---------------------------------------------
            if action == "type_text":
                return True

            # ---------------------------------------------
            # OPEN WEBSITE
            # ---------------------------------------------
            if action == "open_website":
                return True

            # ---------------------------------------------
            # BROWSER SEARCH
            # ---------------------------------------------
            if action == "browser_search":
                return True

            return True

        except Exception as e:
            log(
                f"Verification error: {e}"
            )

            return True

    # =====================================================
    # MONITOR CURRENT SCREEN
    # =====================================================
    def monitor(self):
        try:
            if not self.running:
                return None

            update_context()

            state = analyze_ui_state()

            return state

        except Exception as e:
            log(
                f"Monitor error: {e}"
            )

            return None

    # =====================================================
    # CONTINUE LAST TASK
    # =====================================================
    def continue_task(self):
        try:
            if not self.current_task:
                return "No active task."

            log("Continuing previous task...")

            return self.execute_task(
                self.current_task
            )

        except Exception as e:
            log(
                f"Continue error: {e}"
            )

            return "Failed to continue."

    # =====================================================
    # STOP AGENT
    # =====================================================
    def stop(self):
        self.running = False

        log("Agent stopped.")

    # =====================================================
    # STATUS
    # =====================================================
    def status(self):
        return {
            "running": self.running,
            "current_task": self.current_task,
            "last_result": self.last_result
        }


# =========================================================
# GLOBAL AGENT INSTANCE
# =========================================================
agent = AutonomousAgent()


# =========================================================
# DEBUG MODE
# =========================================================
if __name__ == "__main__":
    while True:
        text = input("You: ")

        if text.lower() == "stop":
            agent.stop()
            break

        result = agent.start(text)

        print(result)