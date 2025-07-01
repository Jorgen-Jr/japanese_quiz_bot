# JLPT Quiz Bot

A Telegram bot that helps users study for the JLPT (Japanese Language Proficiency Test) by sending AI-generated multiple-choice quizzes, using an LLM (LLaMA-3 via ZukiJourney) and Telegram's Bot API.

## Features

- Sends JLPT-style quiz questions (levels N5 to N3)
- Explanations provided in Japanese and English
- Supports:
  - Manual quiz via `/quiz`
  - Scheduled quizzes sent accordingly with the variable `schedule` in the file main.py
  - Explanations on demand using `/explain` as a reply to a quiz
- Caches all quizzes locally in `quiz_cache.jsonl`
- Avoids repetition by checking recent quiz history

## Tools used

- [ZukiJourney](https://zukijourney.com/) (local Ollama LLM gateway)
- [OpenAI client](https://github.com/openai/openai-python)
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)

## Setup

### 1. Clone the repository:

   ```bash
   git clone https://github.com/Jorgen-Jr/japanese_quiz_bot.git
   cd japanese_quiz_bot
   ```

### 2. Create a .env file following the example.env:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
AI_TOKEN=your_zukijourney_or_openai_token
AI_MODEL=llama-3.3-70b-instruct:online
DEBUG=False
QUIZ_INTERVAL=3600
```

### 3. Install dependencies:

```sh
pip install -r requirements.txt
```

### 4. Run the bot:

```py
python main.py
```

Commands
  - `/sensei_start` – Starts sending quizzes to the current chat 3 times a day, accordingly with the variable `schedule` in the main.py file.
  - `/sensei_stop` – Stops sending scheduled quizzes
  - `/quiz` – Sends a single quiz manually
  - `/explain` – Replies with a detailed explanation when used in response to a quiz

File Overview
  - main.py – Main bot logic
  - quiz_cache.jsonl – Stores all previously generated quizzes
  - active_chats.txt – Stores chat IDs for scheduling quizzes
  - .env – Stores secrets and configuration
