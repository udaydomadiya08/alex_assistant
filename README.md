# Alex AI (Bulletproof Edition) 🚀

Alex is a high-speed, 24/7 resilient AI assistant designed for macOS. She features instant wake-word activation, adaptive noise floor tracking, and persistent human-like memory.

## ✨ Key Features
- **Instant Response**: Powered by Groq (LLaMA 3.3) for sub-second latency.
- **Microphone Privacy**: Hardware is released instantly the moment you stop the app (no lingering orange dot).
- **Adaptive VAD**: Real-time noise floor tracking ensures she hears you even in changing environments.
- **3-Layer Memory**: 
  - **Layer 1**: Recent session context.
  - **Layer 2**: Semantic search across previous conversations (ChromaDB).
  - **Layer 3**: Distilled User Profile (she learns your name, preferences, and background over time).
- **Portable & Standalone**: Fully independent architecture that can run from any folder or as a macOS App.

## 🛠️ Quick Setup

### 1. Requirements
- macOS (tested on Apple Silicon)
- Python 3.9+
- [Groq API Key](https://console.groq.com/)
- [OpenRouter API Key](https://openrouter.ai/) (Optional Fallback)

### 2. Installation
Move the folder to `/Applications/AlexAI` and run the setup:
```bash
cd /Applications/AlexAI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory:
```env
GROQ_API_KEY=your_key_here
OPENROUTER_API_KEY=your_key_here
```

## 🚀 How to Run
- **The Clickable Way (Mac Only)**: Double-click `chatbot.app` in your Applications folder.
- **The Terminal Way**:
  ```bash
  python3 chatbot.py
  ```

## 🐧 Windows & Linux Setup (Python Only)
Alex can run on any system with Python 3.9+, but you need a few extra steps for the microphone and audio:

### 1. Install PortAudio (Required for Mic)
- **Windows**: `pip install pipwin` then `pipwin install pyaudio`.
- **Linux (Ubuntu/Debian)**: `sudo apt-get install python3-pyaudio`.

### 2. Install a Command-Line Player (Required for Speech)
Since Windows and Linux don't have `afplay`, install one of these so Alex can speak:
- **Linux**: `sudo apt-get install mpg123`
- **Windows**: Alex will try to use the default system player, but installing `vlc` or `ffmpeg` is recommended for the best experience.

### 3. Running
Once your `.env` is set up, just run:
```bash
python chatbot.py
```
---
*Created with focus on speed, privacy, and long-term intelligence.*
