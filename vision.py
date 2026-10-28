import os
import io
import base64
from PIL import Image
import mss
import pytesseract
import cv2
import numpy as np
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
# SCREENSHOT CAPTURE
# =========================================================
def capture_screen():
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)

        img = Image.frombytes(
            "RGB",
            screenshot.size,
            screenshot.rgb
        )

        return img


# =========================================================
# SAVE SCREENSHOT
# =========================================================
def save_screenshot(path="screen.png"):
    img = capture_screen()
    img.save(path)
    return path


# =========================================================
# OCR TEXT EXTRACTION
# =========================================================
def extract_screen_text():
    img = capture_screen()

    text = pytesseract.image_to_string(img)

    return text.strip()


# =========================================================
# IMAGE TO BASE64
# =========================================================
def image_to_base64(img):
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(
        buffer.getvalue()
    ).decode()

    return encoded


# =========================================================
# OPENAI VISION ANALYSIS
# =========================================================
def analyze_screen(prompt="Describe this screen in detail"):
    img = capture_screen()
    encoded = image_to_base64(img)

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{encoded}"
                        }
                    }
                ]
            }
        ]
    )

    return response.choices[0].message.content


# =========================================================
# GRAPH DETECTOR
# =========================================================
def detect_graph():
    img = capture_screen()

    img_np = np.array(img)

    gray = cv2.cvtColor(
        img_np,
        cv2.COLOR_RGB2GRAY
    )

    edges = cv2.Canny(
        gray,
        50,
        150
    )

    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        100,
        minLineLength=100,
        maxLineGap=10
    )

    if lines is not None:
        return True

    return False


# =========================================================
# FIND TEXT ON SCREEN
# =========================================================
def find_text_on_screen(target):
    text = extract_screen_text()

    return target.lower() in text.lower()


# =========================================================
# ANALYZE CURRENT UI STATE
# =========================================================
def analyze_ui_state():
    prompt = """
Analyze this UI carefully.

Tell:
1. Which app is open
2. What page/screen this is
3. Important visible buttons
4. Important visible texts
5. What user can do next
"""

    return analyze_screen(prompt)


# =========================================================
# UNDERSTAND GRAPH
# =========================================================
def analyze_graph():
    prompt = """
Analyze this graph in detail.

Tell:
1. What kind of graph it is
2. Trend direction
3. Important values
4. Possible meaning
5. Summary
"""

    return analyze_screen(prompt)


# =========================================================
# READ ERROR SCREEN
# =========================================================
def analyze_error_screen():
    prompt = """
Read this error screen carefully.

Explain:
1. What the error is
2. Why it happened
3. How to fix it
"""

    return analyze_screen(prompt)


# =========================================================
# DEBUG
# =========================================================
if __name__ == "__main__":
    print(extract_screen_text())