"""Конфигурация: пути к файлам и загрузка токена бота.

Пути вычисляются относительно корня проекта (родитель папки ``bot/``),
поэтому бот корректно находит данные независимо от того, из какой папки
его запустили.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Корень проекта — каталог, в котором лежит папка bot/
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "storage"

# Подхватываем .env из корня проекта (не блокируемся, если файла нет)
load_dotenv(BASE_DIR / ".env")


def bot_token() -> str:
    """Возвращает токен бота из переменной окружения ``BOT_TOKEN``.

    :raises RuntimeError: если токен не задан — с понятной подсказкой.
    """
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "Не задан BOT_TOKEN.\n"
            "Создайте в корне проекта файл .env со строкой:\n"
            "    BOT_TOKEN=123456:ABC-DEF...\n"
            "(шаблон есть в .env.example), а токен возьмите у @BotFather.\n"
            "Затем перезапустите бота."
        )
    return token
