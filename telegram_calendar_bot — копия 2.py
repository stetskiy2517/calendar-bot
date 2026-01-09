import logging
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import dateparser
import speech_recognition as sr
from pydub import AudioSegment
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

from gpt4all import GPT4All

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------- CONFIG ----------------
TG_TOKEN = "8008795023:AAFiGWPFP1vsNy0wqbBmu-pd1eIl87ZB1eE"
MODEL_PATH = "/Users/stetskiy/Library/Application Support/nomic.ai/GPT4All/gpt4all-falcon-newbpe-q4_0.gguf"

LOCAL_TZ = ZoneInfo("Europe/Saratov")

gpt = GPT4All(MODEL_PATH, allow_download=False)

# ---------------- DATE PARSER ----------------
def parse_start_datetime(text: str) -> datetime:
    now = datetime.now(LOCAL_TZ)
    text_l = text.lower()

    # 1️⃣ время: 13 или 13:00
    time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\b", text_l)
    if not time_match:
        raise ValueError(f"Не удалось распознать дату/время: {text}")

    hour = int(time_match.group(1))
    minute = int(time_match.group(2)) if time_match.group(2) else 0

    # 2️⃣ день
    if "послезавтра" in text_l:
        base_date = now.date() + timedelta(days=2)
    elif "завтра" in text_l or "завтро" in text_l:
        base_date = now.date() + timedelta(days=1)
    elif "сегодня" in text_l:
        base_date = now.date()
    else:
        base_date = now.date()
        if hour < now.hour or (hour == now.hour and minute <= now.minute):
            base_date += timedelta(days=1)

    dt = datetime(
        year=base_date.year,
        month=base_date.month,
        day=base_date.day,
        hour=hour,
        minute=minute,
        tzinfo=LOCAL_TZ
    )

    return dt

# ---------------- TITLE ----------------
def extract_title(text: str) -> str:
    try:
        prompt = f"Выдели короткое название события из текста: {text}"
        result = gpt.generate(prompt)
        if isinstance(result, str):
            return result.strip()
    except Exception:
        pass
    return "Событие"

# ---------------- GOOGLE CALENDAR ----------------
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def get_calendar_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)

calendar_service = get_calendar_service()

def create_event(title: str, start_dt: datetime):
    event = {
        "summary": title,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "Europe/Saratov"
        },
        "end": {
            "dateTime": (start_dt + timedelta(hours=1)).isoformat(),
            "timeZone": "Europe/Saratov"
        }
    }
    calendar_service.events().insert(calendarId="primary", body=event).execute()

# ---------------- CORE LOGIC ----------------
async def process_user_text(text: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        title = extract_title(text)
        start_dt = parse_start_datetime(text)
        create_event(title, start_dt)

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Событие создано:\n{title}\n🕒 {start_dt.strftime('%d.%m %H:%M')}"
        )
    except Exception as e:
        logging.error(f"[ERROR] Ошибка генерации события: {e}")
        await context.bot.send_message(chat_id=chat_id, text=str(e))

# ---------------- TEXT HANDLER ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_user_text(update.message.text, update.message.chat_id, context)

# ---------------- VOICE ----------------
def recognize_voice(path: str) -> str:
    audio = AudioSegment.from_file(path)
    wav_path = "temp.wav"
    audio.export(wav_path, format="wav")

    r = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio_data = r.record(source)

    return r.recognize_google(audio_data, language="ru-RU")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await context.bot.get_file(update.message.voice.file_id)
    ogg_path = "voice.ogg"
    await file.download_to_drive(ogg_path)

    try:
        text = recognize_voice(ogg_path)
        logging.info(f"VOICE → TEXT: {text}")
        await process_user_text(text, update.message.chat_id, context)
    except Exception as e:
        logging.error(f"[ERROR] Voice error: {e}")
        await update.message.reply_text("❌ Не удалось распознать голос")

# ---------------- START ----------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(TG_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("🤖 Бот запущен")
    app.run_polling()
