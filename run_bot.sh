#!/bin/bash
set -e

echo "Запуск бота..."

# 1. Проверяем и создаём виртуальное окружение
if [ ! -d "venv" ]; then
    echo "Создаём виртуальное окружение..."
    python3 -m venv venv
fi

# 2. Используем интерпретатор из venv
PYTHON="./venv/bin/python3"
PIP="./venv/bin/pip"

# 3. Обновляем pip и ставим зависимости
echo "Устанавливаем зависимости..."
$PIP install --upgrade pip
$PIP install -r requirements.txt

# 4. Проверяем ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "ffmpeg не найден! Установите ffmpeg."
else
    echo "ffmpeg найден."
fi

# 5. Проверка Flask и dateparser в venv
$PYTHON -c "import flask, dateparser" || {
    echo "❌ Flask или dateparser не установлены!"
    exit 1
}

# 6. Запуск Flask сервера OAuth
echo "🚀 Запуск Flask сервера авторизации..."
$PYTHON oauth_server.py &

FLASK_PID=$!

# 7. Запуск Telegram бота
echo "🤖 Запуск Telegram бота..."
$PYTHON telegram_calendar_bot.py

# 8. После выхода бота останавливаем Flask сервер
echo "🛑 Остановка Flask сервера..."
kill $FLASK_PID || true
