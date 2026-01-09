#!/bin/bash

# ----------------- Настройка -----------------
set -e  # Остановка при ошибках
echo "🚀 Запуск окружения и зависимостей..."

# Виртуальное окружение
if [ -d "venv" ]; then
    echo "Активируем виртуальное окружение..."
    source venv/bin/activate
else
    echo "Создаём виртуальное окружение..."
    python3 -m venv venv
    source venv/bin/activate
fi

# Установка зависимостей
if [ -f "requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo "requirements.txt не найден!"
fi

# Проверка ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "ffmpeg не найден!"
else
    echo "ffmpeg найден."
fi

# ----------------- Запуск Flask + Telegram -----------------
echo "🚀 Запуск Flask сервера авторизации..."
# Flask сервер в фоне
python3 oauth_server.py &  # & — запуск в фоне
FLASK_PID=$!

echo "🤖 Запуск Telegram бота..."
# Бот в основном потоке
python3 telegram_calendar_bot.py

# ----------------- Завершение -----------------
echo "🛑 Остановка Flask сервера..."
kill $FLASK_PID
