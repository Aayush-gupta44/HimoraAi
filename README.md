
# Himora AI
### Intelligence Beyond Conversation.

## 🎥 Video Demonstration

See Himora AI in action.

The demonstration showcases how Himora AI understands voice and text commands, interacts with desktop applications, performs everyday tasks, and responds to general questions through AI-powered conversations.

[![Himora AI – Watch Demonstration]
https://github.com/user-attachments/assets/2c2e309d-cbf5-4721-9ce3-4cc853f86d2f


---

## About the Project

I built Himora AI with a simple idea in mind: interacting with a computer should feel more natural than constantly switching between applications, clicking through menus, and typing instructions.

Himora AI is a Python-based desktop assistant that combines the conversational capabilities of the OpenAI API with voice and text-based desktop automation.

It can answer everyday questions, understand natural-language instructions, open supported applications, and carry out supported tasks on the desktop. For example, a user can simply say "Open WhatsApp" instead of manually searching for and launching the application.

What makes this project interesting to me is the combination of two different capabilities: understanding what a user wants and translating that intention into an action.

## ✨ Key Features

- **AI-powered conversations:** Ask questions and receive responses through the OpenAI API.
- **Voice interaction:** Communicate with Himora AI using spoken instructions.
- **Text commands:** Enter instructions directly through the desktop interface.
- **Desktop automation:** Open supported applications and perform everyday computer operations.
- **Application-specific agents:** Dedicated agents for supported services such as WhatsApp, YouTube, and Gmail.
- **Task planning and execution:** Process actionable requests and coordinate the steps needed to complete them.
- **Visual interaction:** Includes screen and vision-related capabilities for supported workflows.
- **Context and memory:** Includes components for maintaining relevant conversational and task context.

## 🧠 How It Works

Himora AI brings several components together to process a user's request.

1. **Input:** The user provides an instruction through voice or text.
2. **Understanding:** The system processes the request and identifies its intent.
3. **Routing:** The request is directed towards the appropriate processing component.
4. **Planning:** For actionable requests, the system determines the required steps.
5. **Execution:** The relevant agent or desktop component carries out the supported operation.
6. **Response:** Himora AI communicates the result to the user.

For general questions, the system uses its conversational AI capabilities. For desktop commands, it follows the relevant automation workflow.

## 🏗️ Project Architecture

The project is divided into separate Python modules so that different responsibilities can be developed and maintained independently.

| Component | Responsibility |
|---|---|
| `main.py` | Application entry point |
| `ui.py` | Desktop user interface |
| `brain.py` | AI reasoning and conversation |
| `router.py` | Request routing |
| `planner.py` | Task planning |
| `executor.py` | Action execution |
| `autonomous_agent.py` | Autonomous task workflows |
| `reflection.py` | Reflection and evaluation |
| `context.py` | Context management |
| `voice.py` | Voice input |
| `speaker.py` | Speech output |
| `vision.py` | Visual processing |
| `memory.py` | Memory management |
| `whatsapp_agent.py` | WhatsApp automation |
| `youtube_agent.py` | YouTube automation |
| `gmail_agent.py` | Gmail automation |
| `screen_agent.py` | Screen-related operations |
| `browser.py` | Browser interaction |
| `mac_system.py` | macOS system operations |
| `apps.py` | Application management |

## 🛠️ Technologies Used

- **Python** – Core development language.
- **OpenAI API** – Conversational intelligence and language understanding.
- **PyQt** – Desktop graphical interface.
- **Speech Recognition** – Voice command input.
- **Text-to-Speech** – Spoken responses.
- **Desktop Automation** – Interaction with supported applications and system functions.
- **OCR and Visual Processing** – Screen-related information processing.

## 📁 Project Structure

```text
HimoraAI/
│
├── agents/
├── assets/
│
├── main.py
├── ui.py
│
├── brain.py
├── router.py
├── planner.py
├── executor.py
├── autonomous_agent.py
├── reflection.py
├── context.py
│
├── voice.py
├── speaker.py
├── vision.py
│
├── apps.py
├── mac_system.py
├── browser.py
│
├── whatsapp_agent.py
├── youtube_agent.py
├── gmail_agent.py
├── screen_agent.py
│
├── memory.py
├── skills.py
├── utils.py
├── config.py
│
├── requirements.txt
├── .env.example
└── README.md
```

## 🚀 Running Himora AI Locally

### Prerequisites

- Python installed on your system.
- An OpenAI API key.
- A macOS environment for the current desktop automation workflows.

### 1. Clone the repository

```bash
git clone YOUR_REPOSITORY_URL
cd HimoraAI
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure your API key

Create a `.env` file in the project directory:

```env
OPENAI_API_KEY=your_api_key_here
```

Never share your actual API key or commit your `.env` file to GitHub.

### 5. Start the application

```bash
python main.py
```

## 🔭 Future Improvements

Himora AI is an ongoing project, and there is still plenty I would like to explore and improve.

Some areas I hope to work on include:

- More reliable multi-step task execution.
- Better contextual understanding across conversations.
- Support for additional desktop applications.
- Improved visual understanding and screen interaction.
- More advanced task planning and decision-making.
- Greater personalization and memory capabilities.

## 💡 Why I Built It

I have always been interested in artificial intelligence and the possibility of making technology more useful in everyday life.

Working on Himora AI has given me an opportunity to explore how language models can be connected to real-world software operations. It has also helped me understand the challenges involved in building an application that must not only understand instructions but also act on them reliably.

For me, Himora AI is more than a chatbot. It is an ongoing exploration of how conversational intelligence and computer automation can work together.

---

**Developed by Aayush Gupta**

[GitHub](https://github.com/Aayush-gupta44)
