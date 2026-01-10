import os
import json
from flask import Flask, request, redirect
import telebot

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# ================== CONFIG ==================

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

TOKENS_FILE = "tokens.json"

# ================== APP ==================

app = Flask(__name__)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ================== STORAGE ==================

def load_tokens():
    if not os.path.exists(TOKENS_FILE):
        return {}
    with open(TOKENS_FILE, "r") as f:
        return json.load(f)

def save_tokens(tokens):
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f)

# ================== GOOGLE OAUTH ==================

def get_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=f"{BASE_URL}/auth/callback",
    )

# ================== TELEGRAM ==================

@bot.message_handler(content_types=["text"])
def handle_text(message):
    user_id = str(message.from_user.id)
    tokens = load_tokens()

    if user_id not in tokens:
        auth_url = f"{BASE_URL}/auth/{user_id}"
        bot.reply_to(
            message,
            f"🔐 Нужно авторизоваться:\n{auth_url}"
        )
        return

    bot.reply_to(message, f"✅ Токен есть. Твое сообщение: {message.text}")

# ================== WEBHOOK ==================

@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    update = telebot.types.Update.de_json(
        request.data.decode("utf-8")
    )
    bot.process_new_updates([update])
    return "OK", 200

# ================== OAUTH ROUTES ==================

@app.route("/auth/<user_id>")
def auth(user_id):
    flow = get_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=user_id,
        prompt="consent"
    )
    return redirect(auth_url)

@app.route("/auth/callback")
def auth_callback():
    user_id = request.args.get("state")
    code = request.args.get("code")

    flow = get_flow()
    flow.fetch_token(code=code)

    creds = flow.credentials

    tokens = load_tokens()
    tokens[user_id] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    save_tokens(tokens)

    bot.send_message(
        int(user_id),
        "✅ Авторизация прошла успешно. Можешь писать боту."
    )

    return "Авторизация завершена. Можешь вернуться в Telegram."

# ================== HEALTH ==================

@app.route("/")
def health():
    return "OK", 200

# ================== START ==================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
