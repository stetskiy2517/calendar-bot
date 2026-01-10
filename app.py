import os
import json
import logging
from datetime import datetime, timedelta

from flask import Flask, request, redirect
from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

import dateparser
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ---------------- CONFIG ----------------
TG_TOKEN = os.environ["TG_TOKEN"]
SCOPES = ["https://www.googleapis.com/auth/calendar"]
BASE_URL = os.environ["RENDER_EXTERNAL_URL"]

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

telegram_app = Application.builder().token(TG_TOKEN).build()

# ---------------- DATE PARSER ----------------
def parse_datetime(text: str) -> datetime:
    dt = dateparser.parse(
        text,
        languages=["ru"],
        settings={"PREFER_DATES_FROM": "future"},
    )
    if not dt:
        raise ValueError("Не удалось распознать дату и время")
    return dt

# ---------------- GOOGLE ----------------
def get_flow():
    client_config = json.loads(os.environ["GOOGLE_CLIENT_CONFIG"])
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=f"{BASE_URL}/auth/callback"
    )

def get_calendar_service(user_id: int):
    token_path = f"tokens/{user_id}.json"
    if not os.path.exists(token_path):
        return None

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
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

# ---------------- TELEGRAM ----------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    try:
        dt = create_event(user_id, text)
        await update.message.reply_text(
            f"✅ Событие создано\n🕒 {dt.strftime('%d.%m %H:%M')}"
        )
    except RuntimeError:
        auth_url = f"{BASE_URL}/auth/{user_id}"
        await update.message.reply_text(
            f"🔐 Нужно авторизоваться:\n{auth_url}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# ---------------- OAUTH ----------------
@app.route("/auth/<int:user_id>")
def auth(user_id):
    flow = get_flow()
    flow.authorization_url(state=str(user_id), prompt="consent")
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

# ---------------- WEBHOOK ----------------
@app.route("/telegram/webhook", methods=["POST"])
async def telegram_webhook():
    update = Update.de_json(request.json, telegram_app.bot)
    await telegram_app.process_update(update)
    return "ok"

# ---------------- START ----------------
if __name__ == "__main__":
    import asyncio
asyncio.run(telegram_app.bot.set_webhook(f"{BASE_URL}/telegram/webhook"))

    app.run(host="0.0.0.0", port=10000)
