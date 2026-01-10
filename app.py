import os
import json
import logging
import asyncio
import threading
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Я календарь-бот.\nНапиши: «Завтра в 15 встреча»"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"HANDLE TEXT: {update.effective_user.id} -> {update.message.text}")
    user_id = update.effective_user.id
    text = update.message.text

    try:
        dt = create_event(user_id, text)
        await update.message.reply_text(
            f"✅ Событие создано\n🕒 {dt.strftime('%d.%m %H:%M')}"
        )
    except RuntimeError:
        await update.message.reply_text(
            f"🔐 Нужно авторизоваться:\n{BASE_URL}/auth/{user_id}"
        )
    except Exception as e:
        logger.exception(e)
        await update.message.reply_text("❌ Ошибка при создании события")


telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# ================= DATE PARSER =================
def parse_datetime(text: str) -> datetime:
    dt = dateparser.parse(
        text,
        languages=["ru"],
        settings={"PREFER_DATES_FROM": "future"},
    )
    if not dt:
        raise ValueError("Не удалось распознать дату")
    return dt

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

    # Отправляем обработку в отдельный event loop
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
