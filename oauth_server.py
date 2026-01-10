import os
from flask import Flask, request, redirect, jsonify
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

app = Flask(__name__)

# ---------------- HELPER FUNCTIONS ----------------
def get_flow():
    """Создаёт Flow для OAuth"""
    return Flow.from_client_secrets_file(
        'credentials.json',
        scopes=SCOPES,
        redirect_uri=f"{os.environ.get('RENDER_EXTERNAL_URL')}/auth/callback"
    )

def save_user_token(user_id: str, creds: Credentials):
    token_path = f"tokens/{user_id}.json"
    os.makedirs("tokens", exist_ok=True)
    with open(token_path, "w") as f:
        f.write(creds.to_json())

def load_user_token(user_id: str):
    token_path = f"tokens/{user_id}.json"
    if os.path.exists(token_path):
        return Credentials.from_authorized_user_file(token_path, SCOPES)
    return None

# ---------------- ROUTES ----------------
@app.route("/auth/<user_id>")
def auth(user_id):
    """Ссылка для пользователя, чтобы пройти авторизацию"""
    creds = load_user_token(user_id)
    if creds and creds.valid:
        return f"✅ Вы уже авторизованы, user_id={user_id}"
    flow = get_flow()
    auth_url, _ = flow.authorization_url(prompt="consent")
    return redirect(auth_url)

@app.route("/auth/callback")
def auth_callback():
    """Обработчик redirect от Google OAuth"""
    code = request.args.get("code")
    state = request.args.get("state")  # user_id можно передавать через state
    if not code or not state:
        return "❌ Ошибка: code или state отсутствует", 400

    flow = get_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    save_user_token(state, creds)
    return f"✅ Авторизация завершена! Теперь вернитесь в Telegram. user_id={state}"

# ---------------- MAIN ----------------
if __name__ == "__main__":
    # Render задаёт порт через переменную PORT
    port = int(os.environ.get("PORT", 10000))
    # Render External URL (нужен для OAuth redirect)
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not external_url:
        print("⚠️ Внимание: переменная RENDER_EXTERNAL_URL не задана. Укажите её для корректного OAuth redirect.")
    app.run(host="0.0.0.0", port=port)
