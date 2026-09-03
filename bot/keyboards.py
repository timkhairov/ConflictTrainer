"""Конструкторы inline-клавиатур и константы callback_data.

callback_data ограничена Telegram 1–64 байт, поэтому id конфликтогенов
рекомендуется держать короткими (латиницей). Префиксы не дают callback'ам
пересекаться между разделами.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .models import Conflictogen

# --- callback-префиксы ---
CB_MENU_START_TRAINING = "menu:start_training"
CB_MENU_STATS = "menu:stats"
CB_MENU_ABOUT = "menu:about"
CB_TOGGLE = "cg:"            # cg:<id> — переключить конфликтоген
CB_SUBMIT = "do:submit"      # отправить ответ (отдельный префикс, не пересекается с "cg:")
CB_NEXT = "flow:next"        # следующее упражнение
CB_TO_MENU = "flow:menu"     # вернуться в главное меню


def main_menu() -> InlineKeyboardMarkup:
    """Главное меню бота."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Начать тренировку", callback_data=CB_MENU_START_TRAINING)],
            [
                InlineKeyboardButton(text="📊 Мой прогресс", callback_data=CB_MENU_STATS),
                InlineKeyboardButton(text="ℹ️ Что такое конфликтоген", callback_data=CB_MENU_ABOUT),
            ],
        ]
    )


def exercise_keyboard(conflictogens: list[Conflictogen], selected: set[str]) -> InlineKeyboardMarkup:
    """Клавиатура выбора: по кнопке на конфликтоген + кнопка «Готово».

    Выбранные помечаются «✓», невыбранные — «•». Кнопка обновляется на месте,
    поэтому порядок и состав сохраняются.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for cg in conflictogens:
        mark = "✓ " if cg.id in selected else "• "
        rows.append(
            [InlineKeyboardButton(text=f"{mark}{cg.name}", callback_data=f"{CB_TOGGLE}{cg.id}")]
        )
    rows.append([InlineKeyboardButton(text="✅ Готово", callback_data=CB_SUBMIT)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def feedback_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после проверки ответа."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Следующее упражнение", callback_data=CB_NEXT)],
            [InlineKeyboardButton(text="🏠 В меню", callback_data=CB_TO_MENU)],
        ]
    )
