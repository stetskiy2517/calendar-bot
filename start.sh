#!/bin/bash
# =============================
# Скрипт запуска для Render
# =============================

# Обновляем пакеты и устанавливаем FFmpeg
apt-get update
apt-get install -y ffmpeg

# Запускаем Python приложение
python app.py
