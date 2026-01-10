import os
import json
import logging
import asyncio
import threading
import re
from datetime import datetime, timedelta

from flask import Flask, request, redirect
from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)
import dateparser
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from pydub import AudioSegment
import whisper

# ================= CONFIG =================
TG_TOKEN = os.environ["TG_TOKEN"]
BASE_URL = os.environ["RENDER_EXTERNAL_URL"]
SCOPES = ["https://www.googleapis.com/auth/calendar"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ================= ASYNC LOOP =================
event_loop = asyncio.new_event_loop()


def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


threading.Thread(target=start_loop, args=(event_loop,), daemon=True).start()

# ================= TELEGRAM =================
telegram_app = Application.builder().token(TG_TOKEN).build()

# ================= DATE PARSER =================
WEEKDAYS = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
    "воскресенье": 6,
}


def parse_datetime(text: str) -> datetime:
    text = text.lower()
    now = datetime.now()
    
    # Сначала проверяем, есть ли указание дня недели
    for day_name, day_idx in WEEKDAYS.items():
        if day_name in text:
            days_ahead = (day_idx - now.weekday() + 7) % 7
            if days_ahead == 0:
                days_ahead = 7
            # Попытка найти время в тексте
            time_match = re.search(r"(\d{1,2})[:.]?(\d{0,2})?", text)
            hour, minute = 9, 0
            if time_match:
                hour = int(time_match.group(1))
                if time_match.group(2) and time_match.group(2).isdigit():
                    minute = int(time_match.group(2))
            return (now + timedelta(days=days_ahead)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
    
    # Если день недели не найден — используем dateparser
    dt = dateparser.parse(
        text,
        languages=["ru"],
        settings={"PREFER_DATES_FROM": "future"},
    )
    if dt:
        return dt

    raise ValueError(f"Не удалось распознать дату из текста: {text}")

# ================= GOOGLE CALENDAR =================
def get_flow():
    client_config = json.loads(os.environ["GOOGLE_CLIENT_CONFIG"])
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=f"{BASE_URL}/auth/callback",
    )


def get_calendar_service(user_id: int):
    path = f"tokens/{user_id}.json"
    if not os.path.exists(path):
        return None
    creds = Credentials.from_authorized_user_file(path, SCOPES)
    return build("calendar", "v3", credentials=creds)


def create_event(user_id: int, text: str):
    service = get_calendar_service(user_id)
    if not service:
        raise RuntimeError("AUTH_REQUIRED")

    start = parse_datetime(text)

    event = {
        "summary": text,
        "start": {"dateTime": start.isoformat(), "timeZone": "Europe/Saratov"},
        "end": {
            "dateTime": (start + timedelta(hours=1)).isoformat(),
            "timeZone": "Europe/Saratov",
        },
    }

    service.events().insert(calendarId="primary", body=event).execute()
    return start

# ================= WHISPER =================
whisper_model = whisper.load_model("tiny")  # можно выбрать другую модель

def transcribe_audio(file_path: str) -> str:
    """Конвертирует аудио в WAV и распознаёт текст через Whisper"""
    wav_path = file_path + ".wav"
    audio = AudioSegment.from_file(file_path)
    audio.export(wav_path, format="wav")
    result = whisper_model.transcribe(wav_path)
    return result["text"]

# ================= TELEGRAM HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Я календарь-бот.\nНапиши текст или отправь голосовое сообщение, например: «Завтра в 15 встреча»"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    try:
        dt = create_event(user_id, text)
        await update.message.reply_text(
            f"✅ Событие создано\n🕒 {dt.strftime('%d.%m %H:%M')}"
        )
    except RuntimeError:
        await update.message.reply_text(f"🔐 Нужно авторизоваться:\n{BASE_URL}/auth/{user_id}")
    except Exception as e:
        logger.exception(e)
        await update.message.reply_text("❌ Ошибка при создании события")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    voice = update.message.voice
    if not voice:
        await update.message.reply_text("❌ Нет голосового сообщения")
        return

    try:
        file = await context.bot.get_file(voice.file_id)
        ogg_path = f"voice_{user_id}.ogg"
        await file.download_to_drive(ogg_path)

        text = transcribe_audio(ogg_path)
        dt = create_event(user_id, text)
        await update.message.reply_text(
            f"🎤 Распознано: {text}\n✅ Событие создано\n🕒 {dt.strftime('%d.%m %H:%M')}"
        )
    except RuntimeError:
        await update.message.reply_text(f"🔐 Нужно авторизоваться:\n{BASE_URL}/auth/{user_id}")
    except Exception as e:
        logger.exception(e)
        await update.message.reply_text("❌ Ошибка при обработке голосового сообщения")


telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
telegram_app.add_handler(MessageHandler(filters.VOICE, handle_voice))

# ================= OAUTH =================
@app.route("/auth/<int:user_id>")
def auth(user_id):
    flow = get_flow()
    url, _ = flow.authorization_url(
        state=str(user_id),
        prompt="consent",
        access_type="offline",
    )
    return redirect(url)


@app.route("/auth/callback")
def callback():
    code = request.args["code"]
    user_id = request.args["state"]

    flow = get_flow()
    flow.fetch_token(code=code)

    os.makedirs("tokens", exist_ok=True)
    with open(f"tokens/{user_id}.json", "w") as f:
        f.write(flow.credentials.to_json())

    return "✅ Авторизация завершена. Вернись в Telegram."

# ================= WEBHOOK =================
@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    update = Update.de_json(
        request.get_json(force=True),
        telegram_app.bot
    )

    event_loop.call_soon_threadsafe(
        asyncio.create_task,
        telegram_app.process_update(update)
    )

    return "ok"

# ================= START =================
if __name__ == "__main__":
    async def startup():
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.bot.set_webhook(f"{BASE_URL}/telegram/webhook")

    asyncio.run(startup())
    app.run(host="0.0.0.0", port=10000)
