"""Конструкторы inline-клавиатур и константы callback_data.

callback_data ограничена Telegram 1–64 байт, поэтому id конфликтогенов
рекомендуется держать короткими (латиницей). Префиксы не дают callback'ам
пересекаться между разделами.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .models import Conflictogen, Domain, Subject

# --- callback-префиксы ---
CB_MENU_START_TRAINING = "menu:start_training"
CB_MENU_STATS = "menu:stats"
CB_MENU_ABOUT = "menu:about"
CB_DOMAIN = "dom:"           # dom:<id> — выбрать сферу жизни
CB_SUBJECT = "sub:"          # sub:<id> — выбрать тему внутри сферы
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


def domain_keyboard(domains: list[Domain]) -> InlineKeyboardMarkup:
    """Выбор сферы жизни: по кнопке на сферу + возврат в главное меню.

    Если у сферы задан icon — он становится префиксом подписи («💼 Работа»),
    без icon кнопка показывает только название.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for d in domains:
        text = f"{d.icon} {d.name}" if d.icon else d.name
        rows.append([InlineKeyboardButton(text=text, callback_data=f"{CB_DOMAIN}{d.id}")])
    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data=CB_TO_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subject_keyboard(subjects: list[Subject]) -> InlineKeyboardMarkup:
    """Выбор темы внутри сферы: по кнопке на тему + возврат в главное меню.

    `subjects` — уже отфильтрованный по сфере список (фильтрует вызывающий,
    см. handlers.exercise.choose_subject).
    """
    rows: list[list[InlineKeyboardButton]] = []
    for s in subjects:
        rows.append([InlineKeyboardButton(text=s.name, callback_data=f"{CB_SUBJECT}{s.id}")])
    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data=CB_TO_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
