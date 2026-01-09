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
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# ---------------- CONFIG ----------------
TG_TOKEN = "8008795023:AAFiGWPFP1vsNy0wqbBmu-pd1eIl87ZB1eE"
MODEL_PATH = "/Users/stetskiy/Library/Application Support/nomic.ai/GPT4All/gpt4all-falcon-newbpe-q4_0.gguf"
OAUTH_SERVER_URL = "http://localhost:5000/auth"

gpt = GPT4All(MODEL_PATH, allow_download=False)

USER_TOKENS_DIR = "user_tokens"
if not os.path.exists(USER_TOKENS_DIR):
    os.makedirs(USER_TOKENS_DIR)

# ---------------- HELPERS ----------------
def load_user_token(user_id: int):
    token_path = os.path.join(USER_TOKENS_DIR, f"{user_id}_token.json")
    if os.path.isfile(token_path):
        return Credentials.from_authorized_user_file(token_path, ["https://www.googleapis.com/auth/calendar.events"])
    return None

def create_event(user_id: int, title: str, start_dt: datetime):
    creds = load_user_token(user_id)
    if not creds or not creds.valid:
        raise ValueError(f"Необходимо авторизоваться: {OAUTH_SERVER_URL}/{user_id}")
    service = build("calendar", "v3", credentials=creds)
    event = {
        "summary": title,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Saratov"},
        "end": {"dateTime": (start_dt + timedelta(hours=1)).isoformat(), "timeZone": "Europe/Saratov"}}
    service.events().insert(calendarId="primary", body=event).execute()

def parse_start_datetime(text: str) -> datetime:
    now = datetime.now()
    text_l = text.lower()
    time_match = re.search(r"\b(\d{1,2}):(\d{2})\b", text_l)
    if not time_match:
        raise ValueError(f"Не удалось распознать дату/время: {text}")
    hour, minute = map(int, time_match.groups())
    if "послезавтра" in text_l: base_date = now.date() + timedelta(days=2)
    elif "завтра" in text_l or "завтро" in text_l: base_date = now.date() + timedelta(days=1)
    elif "сегодня" in text_l: base_date = now.date()
    else:
        dt = dateparser.parse(text, languages=["ru"], settings={"PREFER_DATES_FROM":"future","RELATIVE_BASE":now,"RETURN_AS_TIMEZONE_AWARE":False})
        if not dt: raise ValueError(f"Не удалось распознать дату/время: {text}")
        return dt
    return datetime.combine(base_date, datetime.min.time()).replace(hour=hour, minute=minute)

def extract_title(text: str) -> str:
    try:
        result = gpt.generate(f"Выдели короткое название события из текста: {text}")
        if isinstance(result, str): return result.strip()
    except Exception: pass
    return "Встреча"

async def process_user_text(text: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        title = extract_title(text)
        start_dt = parse_start_datetime(text)
        create_event(chat_id, title, start_dt)
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Событие создано:\n{title}\n🕒 {start_dt.strftime('%d.%m %H:%M')}")
    except ValueError as ve:
        if "Необходимо авторизоваться" in str(ve):
            await context.bot.send_message(chat_id=chat_id, text=str(ve))
        else:
            logging.error(f"[ERROR] {ve}")
            await context.bot.send_message(chat_id=chat_id, text=str(ve))
    except Exception as e:
        logging.error(f"[ERROR] {e}")
        await context.bot.send_message(chat_id=chat_id, text=str(e))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    await process_user_text(text, update.message.chat_id, context)

# ---------------- VOICE ----------------
def recognize_voice(path: str) -> str:
    audio = AudioSegment.from_file(path)
    wav_path = "temp.wav"
    audio.export(wav_path, format="wav")
    import speech_recognition as sr
    r = sr.Recognizer()
    with sr.AudioFile(wav_path) as source: audio_data = r.record(source)
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

# ---------------- START BOT ----------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(TG_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("🤖 Бот запущен")
    app.run_polling()
