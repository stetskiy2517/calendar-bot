import os
from flask import Flask, request, redirect
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Папка для токенов пользователей
TOKEN_DIR = "tokens"
os.makedirs(TOKEN_DIR, exist_ok=True)

# ----------------- Роут авторизации -----------------
@app.route("/auth/<int:user_id>")
def auth(user_id):
    """Создаём ссылку OAuth для пользователя"""
    flow = Flow.from_client_secrets_file(
        'credentials.json',
        scopes=SCOPES,
        redirect_uri=f"{request.url_root}callback/{user_id}"
    )
    auth_url, _ = flow.authorization_url(prompt='consent')
    return redirect(auth_url)

# ----------------- Callback после авторизации -----------------
@app.route("/callback/<int:user_id>")
def callback(user_id):
    """Получаем код от Google, меняем на токен, сохраняем"""
    code = request.args.get("code")
    if not code:
        return "❌ Ошибка: код авторизации не получен."

    flow = Flow.from_client_secrets_file(
        'credentials.json',
        scopes=SCOPES,
        redirect_uri=f"{request.url_root}callback/{user_id}"
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Сохраняем токен
    token_path = os.path.join(TOKEN_DIR, f"token_{user_id}.json")
    with open(token_path, "w") as f:
        f.write(creds.to_json())

    return f"✅ Авторизация пройдена! Можете вернуться в Telegram и продолжить работу."

# ----------------- Утилита для получения сервиса -----------------
def get_calendar_service(user_id: int):
    token_path = os.path.join(TOKEN_DIR, f"token_{user_id}.json")
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds and creds.valid:
        return build("calendar", "v3", credentials=creds)
    return None

# ----------------- Запуск -----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
