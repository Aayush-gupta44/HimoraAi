import os
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
# BASE GPT CALL
# =========================================================
def run_skill(system_prompt, user_input):
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_input
                }
            ],
            temperature=0.4
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"Skill error: {e}"


# =========================================================
# CODING SKILL
# =========================================================
def coding_skill(user_input):
    prompt = """
You are Himora Coding Expert.

Rules:
- Write clean code
- Explain clearly
- Fix bugs
- Optimize code
- Give professional solutions
"""

    return run_skill(prompt, user_input)


# =========================================================
# DEBUGGING SKILL
# =========================================================
def debug_skill(user_input):
    prompt = """
You are Himora Debug Expert.

Your job:
- Identify bugs
- Explain errors
- Fix code
- Improve stability
"""

    return run_skill(prompt, user_input)


# =========================================================
# MATH SKILL
# =========================================================
def math_skill(user_input):
    prompt = """
You are Himora Math Expert.

Your job:
- Solve accurately
- Explain step-by-step
- Be precise
"""

    return run_skill(prompt, user_input)


# =========================================================
# FINANCE SKILL
# =========================================================
def finance_skill(user_input):
    prompt = """
You are Himora Finance Expert.

Your job:
- Analyze stocks
- Explain trends
- Explain markets
- Analyze charts
"""

    return run_skill(prompt, user_input)


# =========================================================
# RESEARCH SKILL
# =========================================================
def research_skill(user_input):
    prompt = """
You are Himora Research Expert.

Your job:
- Deep analysis
- Structured explanation
- Compare ideas
- Give high quality information
"""

    return run_skill(prompt, user_input)


# =========================================================
# SUMMARIZATION SKILL
# =========================================================
def summarize_skill(user_input):
    prompt = """
You are Himora Summarization Expert.

Your job:
- Summarize clearly
- Keep key ideas
- Make it easy
"""

    return run_skill(prompt, user_input)


# =========================================================
# GENERAL SKILL ROUTER
# =========================================================
def route_skill(user_input):
    text = user_input.lower()

    if any(word in text for word in [
        "code", "python", "javascript",
        "html", "css", "flutter"
    ]):
        return coding_skill(user_input)

    if any(word in text for word in [
        "bug", "error", "fix", "traceback"
    ]):
        return debug_skill(user_input)

    if any(word in text for word in [
        "solve", "equation", "math",
        "calculate"
    ]):
        return math_skill(user_input)

    if any(word in text for word in [
        "stock", "finance", "market",
        "investment", "share"
    ]):
        return finance_skill(user_input)

    if any(word in text for word in [
        "research", "analyze", "compare"
    ]):
        return research_skill(user_input)

    if any(word in text for word in [
        "summary", "summarize", "short"
    ]):
        return summarize_skill(user_input)

    return None