from flask import Flask, request
import os
import json

app = Flask(__name__)

USER_TOKENS_DIR = "user_tokens"
if not os.path.exists(USER_TOKENS_DIR):
    os.makedirs(USER_TOKENS_DIR)

@app.route("/oauth")
def oauth_redirect():
    user_id = request.args.get("user_id")
    code = request.args.get("code")

    # ===== Здесь ваша функция получения токена =====
    token_data = fetch_token_from_google(code)  # ваша существующая логика получения токена
    # ==============================================

    # Сохраняем токен для пользователя
    token_path = os.path.join(USER_TOKENS_DIR, f"{user_id}_token.json")
    with open(token_path, "w") as f:
        json.dump(token_data, f)

    return f"Авторизация завершена! Вы можете вернуться в Telegram и продолжить работу с ботом."
