"""Catch-all: вежливый ответ на неподдерживаемые сообщения и callback'и.

Важно: этот роутер подключается последним (см. handlers/__init__.py),
чтобы не перехватывал уже обработанные события.

Ответ на «чужие» сообщения даём только в личном чате: в группах/супергруппах
молчим, чтобы не отвлекать всех участников.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message

router = Router(name="fallback")

_HINT = "Пока я работаю только через меню 🙂\n\nНажми /start, чтобы открыть главное меню."


@router.message(F.chat.type == ChatType.PRIVATE)
async def fallback_message(message: Message):
    await message.answer(_HINT)


@router.callback_query()
async def fallback_callback(call: CallbackQuery):
    await call.answer("Неизвестное действие. Вернись в меню — /start.", show_alert=True)
