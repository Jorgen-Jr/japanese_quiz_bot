import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (ApplicationBuilder, CommandHandler,ContextTypes, JobQueue, CallbackQueryHandler)
import json
from openai import OpenAI
from pathlib import Path
import random
from datetime import time
from collections import deque

load_dotenv()

AI_TOKEN = os.getenv("AI_TOKEN")
AI_MODEL = os.getenv("AI_MODEL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
QUIZ_INTERVAL = int(os.getenv("QUIZ_INTERVAL", "3600"))
ACTIVE_CHATS_FILE = Path(os.getenv("ACTIVE_CHATS_FILE"))
QUIZ_CACHE_FILE = Path(os.getenv("QUIZ_CACHE_FILE"))

schedule = [
    ("morning", time(hour=9-3, minute=0)),
    ("morning_2", time(hour=11-3, minute=0)),
    ("afternoon", time(hour=17-3, minute=0)),
    ("afternoon_2", time(hour=19-3, minute=0)),
    ("evening", time(hour=21-3, minute=0))
]

QUIZ_PROMPT = """
Generate a random JLPT multiple choice question from levels N5 to N1 as a JSON.
 - Be as didactive as possible.
 - Use old JLPT tests available in your database.
 - Use english on N5 and N4 questions.
Include:
- question (Inform the level of the question)
- 4 options (A, B, C, D)
- correct option index (0-based) without this information, the final JSON object will become unusable.
- explanation for the correct answer, Simple text with 200 characters and 1 line feed max, explaining why the correct option is correct, use english and japanese to explain.

Return ONLY the JSON object. Folow the scructure strictly, Follow these examples:

```jsonl
{"question":"[N1] 彼の話し方は論理的で、説得力に_______。","options":["富んでいる","欠けている","足りている","優れている"],"correct_option_id":0,"explanation":"『説得力に富む』 means 'full of persuasiveness'."}
{"question":"[N5] How do you say 'river' in Japanese?","options":["山","川","海","空"],"correct_option_id":1,"explanation":"『川』 means 'river' and is pronounced 'かわ'."}
{"question":"[N4] 昨日は友達と公園で_______。","options":["遊びました","勉強しました","働きました","休みました"],"correct_option_id":0,"explanation":"『遊びました』 means 'played'. Yesterday, played with friends in the park."}
{"question":"[N3] この料理は見た目は美しい_______、味は普通だ。","options":["けれど","ので","から","が"],"correct_option_id":3,"explanation":"『が』 is used to express contrast politely. Although it looks beautiful, the taste is ordinary."}
{"question":"[N2] 彼女は優しい_______、厳しい時もある。","options":["けれども","ので","から","のに"],"correct_option_id":0,"explanation":"『けれども』 means 'although'. She is kind, but sometimes strict."}
{"question":"[N1] この理論は複雑で、理解するのが_______。","options":["難しい","簡単な","早い","遅い"],"correct_option_id":0,"explanation":"『難しい』 means 'difficult'. This theory is complex and hard to understand."}
{"question":"[N5] What does the kanji '犬' mean?","options":["Cat","Bird","Dog","Fish"],"correct_option_id":2,"explanation":"『犬』 means 'dog' and is pronounced 'いぬ'."}
`
"""

EXPLAIN_PROMPT = """
You are an expert Japanese language teacher.

The user submitted the following JLPT-style quiz question:

{question}

Provide a more detailed explanation of the correct answer.
Explain it using English, and include grammar, usage, and nuance.
Don't ask follow up questions, and the introduction message (Ex. "Certainly! Here's a detailed explanation for the JLPT N4 quiz question:") is already embedded so it's not needed.
Please deliver the response in plain text without any Markdown or formatting. Provide the output as raw text.
"""


client = OpenAI(base_url="https://api.zukijourney.com/v1", api_key=AI_TOKEN)

def load_active_chats() -> set[int]:
    if not ACTIVE_CHATS_FILE.exists():
        return set()
    try:
        with ACTIVE_CHATS_FILE.open("r", encoding="utf-8") as f:
            return set(int(line.strip()) for line in f)
    except Exception as e:
        print("Error reading active_chats.txt:", e)
        return set()

def save_active_chats(chats: set[int]):
    try:
        with ACTIVE_CHATS_FILE.open("w", encoding="utf-8") as f:
            for chat_id in chats:
                f.write(f"{chat_id}\n")
    except Exception as e:
        print("Error writing active_chats.txt:", e)

active_chats = load_active_chats()

def append_quiz_to_cache(quiz: dict):
    try:
        with QUIZ_CACHE_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(quiz, ensure_ascii=False) + "\n")
        print("Quiz appended to cache.")
        with open(QUIZ_CACHE_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            line_index = len(lines) - 1
            return line_index
    except Exception as e:
        print("Failed to cache quiz:", e)

def load_random_cached_quiz() -> tuple[dict, int] | None:
    try:
        if not QUIZ_CACHE_FILE.exists():
            print("No quiz cache found.")
            return None

        with QUIZ_CACHE_FILE.open("r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        if not lines:
            print("Quiz cache found, but empty.")
            return None

        index = random.randrange(len(lines))
        quiz = json.loads(lines[index])
        return quiz, index

    except Exception as e:
        print("Error loading cached quiz:", e)
        return None

def load_recent_quiz_questions(limit=5):
    if not QUIZ_CACHE_FILE.exists():
        return []

    recent_questions = deque(maxlen=limit)
    try:
        with QUIZ_CACHE_FILE.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines[-limit:]:
            quiz = json.loads(line)
            recent_questions.append(quiz.get("question", ""))
    except Exception as e:
        print("Error loading recent quiz questions:", e)

    return list(recent_questions)

def schedule_quiz_job(chat_id: int, job_queue: JobQueue, first: int = 0):
    for label, when in schedule:
        job_name = f"{label}-{chat_id}"

        # Remove any existing job with the same name
        for job in job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()

        job_queue.run_daily(
            callback=send_group_quiz,
            time=when,
            chat_id=chat_id,
            name=job_name
        )

        print(f"Scheduled {label} quiz for chat {chat_id} at {when.strftime('%H:%M')}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Group quiz schedulle interval
    chat_id = update.effective_chat.id
    if chat_id not in active_chats:
        active_chats.add(chat_id)
        save_active_chats(active_chats)

    schedule_quiz_job(chat_id, context.job_queue)
    await update.message.reply_text("Bot started, will be sending quizes anytime soon!")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    job_name = str(chat_id)

    jobs = context.job_queue.get_jobs_by_name(job_name)
    if not jobs:
        await update.message.reply_text("No active quiz job found for this chat.")
        return

    for job in jobs:
        job.schedule_removal()

    active_chats.discard(chat_id)
    save_active_chats(active_chats)

    print("Job removed for CHAT:", chat_id)
    await update.message.reply_text("Sensei has been stopped for this group.")

def generate_quiz(level = None):
    print('Generating quiz...')

    try:
        recent_questions = load_recent_quiz_questions(limit=5)

        system_message = {
            "role": "system",
            "content": (
                "You are an expert Japanese language teacher creating JLPT quizzes. "
                "Avoid to make questions similar to those asked recently. "
                "Generate varied questions covering different grammar points, vocabulary, "
                "and kanji, from levels N5 to N3."
            )
        }

        messages = [system_message]

        if recent_questions:
            previous_qs_text = "\n".join(f"- {q}" for q in recent_questions)
            messages.append({
                "role": "user",
                "content": f"Previously asked questions:\n{previous_qs_text}"
            })

        # Finally, append the actual prompt requesting a new quiz
        messages.append({"role": "user", "content": QUIZ_PROMPT})
        if(level):
            messages.append({"role": "user", "content": f"Generate a JLPT {level} level quiz this time."})
        
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            stream=False
        )

        content = response.choices[0].message.content.strip()
        print(response)
        print('=================================')
        zj_usage = response.usage.zj_usage
        print('Multiplier:', zj_usage['multiplier'])
        print('Prompt Cost:', zj_usage['prompt_cost'])
        print('Completion Cost:', zj_usage['completion_cost'])
        print('Total Cost:', zj_usage['total_cost'])
        print('CREDITS REMAINING:', zj_usage['credits_remaining'])
        print('=================================')
        # Optional: fix LLM wrapping output in code blocks
        if content.startswith("```"):
            content = content.strip("`").strip("json").strip()

        quiz = json.loads(content)
        line_index = append_quiz_to_cache(quiz)

        return quiz, line_index

    except Exception as e:
        print("Error generating quiz:", e)
        print("Falling back to cached quiz.")
        return load_random_cached_quiz()

async def send_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    level = None
    if context.args:
        level_candidate = context.args[0].upper()
        if level_candidate in ["N1", "N2", "N3", "N4", "N5"]:
            level = level_candidate

    quiz, line_index = generate_quiz(level=level)

    if quiz is None:
        await update.message.reply_text("Sorry, I couldn't generate a quiz right now.")
        return

    message = await update.message.reply_poll(
        question=quiz["question"],
        options=quiz["options"],
        type='quiz',
        correct_option_id=quiz["correct_option_id"],
        is_anonymous=True,
        explanation=quiz["explanation"]
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Explain-me", callback_data=f"explain|{line_index}")]
    ])
    await context.bot.send_message(
        chat_id=chat_id,
        text="まぁTap here if you want me to explain the quiz ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧",
        reply_markup=keyboard
    )

async def send_group_quiz(context: ContextTypes.DEFAULT_TYPE):
    print(f"[SEND_QUIZ] Sending quiz to chat {context.job.chat_id}")
    chat_id = context.job.chat_id
    quiz, line_index = generate_quiz()

    if quiz is None:
        await update.message.reply_text("Sorry, I couldn't generate a quiz right now.")
        return

    message = await update.message.reply_poll(
        question=quiz["question"],
        options=quiz["options"],
        type='quiz',
        correct_option_id=quiz["correct_option_id"],
        is_anonymous=True,
        explanation=quiz["explanation"]
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Explain-me", callback_data=f"explain|{line_index}")]
    ])
    await context.bot.send_message(
        chat_id=chat_id,
        text="まぁTap here if you want me to explain the quiz ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧",
        reply_markup=keyboard
    )

async def explain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Generating explanation")
    # Check if the message is a reply
    if not update.message.reply_to_message or not update.message.reply_to_message.poll:
        await update.message.reply_text("クイズのメッセージに /explain って返事してね.")
        return

    poll_message = update.message.reply_to_message
    poll = update.message.reply_to_message.poll
    question = poll.question.strip()

    prompt = EXPLAIN_PROMPT.format(question=question)

    try:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"ちょっと待ってくださいね~🌸"
            )
        except Exception as e:
            print("Error replying to user", e)
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        content = response.choices[0].message.content.strip()

        print('=================================')
        zj_usage = response.usage.zj_usage
        print('Multiplier:', zj_usage['multiplier'])
        print('Prompt Cost:', zj_usage['prompt_cost'])
        print('Completion Cost:', zj_usage['completion_cost'])
        print('Total Cost:', zj_usage['total_cost'])
        print('CREDITS REMAINING:', zj_usage['credits_remaining'])
        print('=================================')

        if content.startswith("```"):
            content = content.strip("`").strip("json").strip()

        await poll_message.reply_text(f"えっと。。\n{content}")

    except Exception as e:
        print("Error generating explanation:", e)
        await update.message.reply_text("ごめんね、今は解説を出せなかったみたい。")

async def handle_explain_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("explain|"):
        return

    try:
        quiz_index = int(data.split("|", 1)[1])
    except ValueError:
        print("Invalid quiz index in callback_data")
        await query.message.reply_text("クイズが見つからなかったみたい。")
        return

    # Read the quiz from the cached JSONL file
    try:
        with open(QUIZ_CACHE_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        quiz_json = lines[quiz_index]
        quiz = json.loads(quiz_json)
    except (IndexError, FileNotFoundError, json.JSONDecodeError) as e:
        print("Error reading quiz from cache:", e)
        await query.message.reply_text("クイズが見つからなかったみたい。")
        return

    question = quiz["question"]
    prompt = EXPLAIN_PROMPT.format(question=question)

    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="ちょっと待ってくださいね~🌸"
        )
    except Exception as e:
        print("Error sending wait message:", e)

    try:
        # Ask the LLM for an explanation
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.strip("`").strip("json").strip()

        zj_usage = response.usage.zj_usage
        print('=================================')
        print('Multiplier:', zj_usage['multiplier'])
        print('Prompt Cost:', zj_usage['prompt_cost'])
        print('Completion Cost:', zj_usage['completion_cost'])
        print('Total Cost:', zj_usage['total_cost'])
        print('CREDITS REMAINING:', zj_usage['credits_remaining'])
        print('=================================')

        # Reply with the explanation
        await query.message.reply_text(f"えっと。。。\n{content}")

    except Exception as e:
        print("Error generating explanation:", e)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="ごめんね、今は解説を出せなかったみたい。"
        )
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("quiz", send_quiz))
    app.add_handler(CommandHandler("explain", explain))
    app.add_handler(CommandHandler("sensei_start", start))
    app.add_handler(CommandHandler("sensei_stop", stop))
    app.add_handler(CallbackQueryHandler(handle_explain_button))

    # Re-add jobs on restart
    print(active_chats)
    for chat_id in active_chats:
        schedule_quiz_job(chat_id, app.job_queue, first=10)
        print(f"Restarting job schedulle for CHAT: {chat_id}")

    print("Bot running...")
    app.run_polling()

