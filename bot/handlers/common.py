"""Общие помощники для обработчиков: безопасный edit и лимиты Telegram.

Используются в start.py / exercise.py / stats.py вместо дублирования
одинаковых try/except в каждом обработчике.
"""
from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

log = logging.getLogger(__name__)

# Вежливый краткий ответ на callback, если что-то пошло не так
ERROR_ANSWER = "Что-то пошло не так, попробуй ещё раз."

# Максимальная длина текста сообщения в символах (лимит Telegram)
TELEGRAM_TEXT_LIMIT = 4096

# Безобидные ошибки editMessage*, которые не должны ломать сценарий
_IGNORED_EDIT_MARKERS = ("message is not modified", "message to edit not found")


def _is_ignored_edit_error(e: TelegramBadRequest) -> bool:
    reason = str(e)
    return any(marker in reason for marker in _IGNORED_EDIT_MARKERS)


async def safe_edit(call: CallbackQuery, text: str, kb) -> None:
    """edit_text, который не падает на безобидных ошибках.

    «message is not modified» (контент не изменился) и «message to edit not
    found» (сообщение удалено/недоступно) — логируем и не пробрасываем,
    чтобы сценарий не ломался. Остальные ошибки пробрасываем дальше.
    """
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if _is_ignored_edit_error(e):
            log.debug("safe_edit: безобидная ошибка, пропускаем: %s", e)
            return
        raise


async def safe_edit_markup(call: CallbackQuery, kb) -> None:
    """edit_reply_markup с той же толерантностью к безобидным ошибкам, что и safe_edit."""
    try:
        await call.message.edit_reply_markup(reply_markup=kb)
    except TelegramBadRequest as e:
        if _is_ignored_edit_error(e):
            log.debug("safe_edit_markup: безобидная ошибка, пропускаем: %s", e)
            return
        raise


def fit_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> str:
    """Обрезает текст под лимит Telegram, не обрывая HTML-разметку.

    Если текст короче лимита — возвращается без изменений. Иначе отрезаем
    так, чтобы не остаться внутри тега («<b>…») и внутри HTML-сущности
    («&qu…»), и добавляем «…» в конце.
    """
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    # Не обрываем тег: отбрасываем «хвост» после последней «<», если за ней нет «>»
    lt, gt = cut.rfind("<"), cut.rfind(">")
    if lt > gt:
        cut = cut[:lt]
    # Не обрываем сущность вида &quot;: отбрасываем «хвост» после последней «&»
    amp, semi = cut.rfind("&"), cut.rfind(";")
    if amp > semi:
        cut = cut[:amp]
    return cut.rstrip() + "…"
