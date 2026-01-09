import logging
import os
import re
from datetime import datetime, timedelta

import dateparser
import speech_recognition as sr
from pydub import AudioSegment
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

from gpt4all import GPT4All
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# ---------------- CONFIG ----------------
TG_TOKEN = "8008795023:AAFiGWPFP1vsNy0wqbBmu-pd1eIl87ZB1eE"
MODEL_PATH = "/Users/stetskiy/Library/Application Support/nomic.ai/GPT4All/gpt4all-falcon-newbpe-q4_0.gguf"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
CLIENT_SECRETS_FILE = "credentials.json"  # твой Google OAuth client
REDIRECT_URI = "http://localhost:5000/oauth2callback"  # должен совпадать с Flask сервером

gpt = GPT4All(MODEL_PATH, allow_download=False)

# ---------------- DATE PARSER ----------------
def parse_start_datetime(text: str) -> datetime:
    now = datetime.now()
    text_l = text.lower()

    # 1️⃣ вытаскиваем время
    time_match = re.search(r"\b(\d{1,2}):(\d{2})\b", text_l)
    if not time_match:
        raise ValueError(f"Не удалось распознать дату/время: {text}")

    hour, minute = map(int, time_match.groups())

    # 2️⃣ определяем день
    if "послезавтра" in text_l:
        base_date = now.date() + timedelta(days=2)
    elif "завтра" in text_l or "завтрo" in text_l:  # небольшая опечатка учтена
        base_date = now.date() + timedelta(days=1)
    elif "сегодня" in text_l:
        base_date = now.date()
    else:
        # пробуем dateparser как fallback
        dt = dateparser.parse(
            text,
            languages=["ru"],
            settings={
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": now,
                "RETURN_AS_TIMEZONE_AWARE": False,
            },
        )
        if not dt:
            raise ValueError(f"Не удалось распознать дату/время: {text}")
        return dt

    dt = datetime.combine(base_date, datetime.min.time()).replace(hour=hour, minute=minute)
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
    return "Встреча"

# ---------------- MULTIUSER AUTH ----------------
def get_user_token_path(chat_id):
    return f"tokens/{chat_id}.json"

def is_user_authorized(chat_id):
    return os.path.exists(get_user_token_path(chat_id))

def get_auth_link(chat_id):
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        state=str(chat_id)
    )
    return auth_url

def get_calendar_service_for_user(chat_id):
    token_path = get_user_token_path(chat_id)
    if not os.path.exists(token_path):
        return None
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    return build("calendar", "v3", credentials=creds)

def create_event(title: str, start_dt: datetime, chat_id: int):
    service = get_calendar_service_for_user(chat_id)
    if not service:
        raise ValueError("Пользователь не авторизован. Сначала пройдите авторизацию.")
    
    event = {
        "summary": title,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Saratov"},
        "end": {"dateTime": (start_dt + timedelta(hours=1)).isoformat(), "timeZone": "Europe/Saratov"},
    }
    service.events().insert(calendarId="primary", body=event).execute()

# ---------------- CORE LOGIC ----------------
async def process_user_text(text: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not is_user_authorized(chat_id):
        auth_link = get_auth_link(chat_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❗ Сначала авторизуйтесь для работы с календарем:\n{auth_link}"
        )
        return

    try:
        title = extract_title(text)
        start_dt = parse_start_datetime(text)
        create_event(title, start_dt, chat_id)

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
    os.makedirs("tokens", exist_ok=True)

    app = ApplicationBuilder().token(TG_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("🤖 Бот запущен")
    app.run_polling()
