"""Статистика прогресса пользователя."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.text_decorations import html_decoration as html

from ..keyboards import CB_MENU_STATS, main_menu
from ..models import Conflictogen
from ..store import Store
from .common import ERROR_ANSWER, fit_text, safe_edit

router = Router(name="stats")

# Статистика — личные данные: в группах показываем только подсказку.
_GROUP_STATS_HINT = "📊 Статистику показываю только в личном чате — напиши мне «/stats» в личке."


def _cg_lines(cg: dict[str, dict[str, int]], conflictogens: list[Conflictogen]) -> list[str]:
    """По одной строке на конфликтоген: сколько раз появлялся и сколько раз найден.

    Порядок — по списку `conflictogens` (порядок файла данных, как в
    тренировочной клавиатуре). Конфликтогены, которых нет в сохранённых данных
    или у которых оба счётчика нулевые, пропускаются молча (защита от
    повреждённых записей и от конфликтогенов, которые ещё не встречались).
    """
    lines: list[str] = []
    for c in conflictogens:
        counts = cg.get(c.id) or {}
        present = int(counts.get("present", 0) or 0)
        correct = int(counts.get("correct", 0) or 0)
        fp = int(counts.get("false_positive", 0) or 0)
        if present == 0 and fp == 0:
            continue
        if present > 0:
            pct = f"{correct / present * 100:.0f}"
            line = f"  • {html.quote(c.name)} — {correct} из {present} ({pct}%)"
            if fp > 0:
                line += f", лишних: {fp}"
        else:
            line = f"  • {html.quote(c.name)} — лишних отметок: {fp}"
        lines.append(line)
    return lines


def _stats_text(s: dict, conflictogens: list[Conflictogen]) -> str:
    attempts = s["attempts"]
    if not attempts:
        return (
            "📊 <b>Твой прогресс</b>\n\n"
            "Ты ещё не проходил(а) ни одного упражнения.\n\n"
            "Нажми «🎯 Начать тренировку», чтобы начать."
        )
    acc = s["accuracy"]
    acc_str = f"{acc * 100:.0f}%" if acc is not None else "—"
    text = (
        "📊 <b>Твой прогресс</b>\n\n"
        f"Попыток: {attempts}\n"
        f"Собрано правильных: {s['total_correct']} из {s['total_possible']}\n"
        f"Точность: {acc_str}\n"
        f"Пройдено упражнений: {len(s['completed'])}"
    )
    lines = _cg_lines(s.get("conflictogens") or {}, conflictogens)
    if lines:
        text += "\n\n🔍 <b>По конфликтогенам:</b>\n" + "\n".join(lines)
    # Гарантируем, что текст не превысит лимит Telegram (4096).
    return fit_text(text)


@router.message(Command("stats"))
async def cmd_stats(
    message: Message,
    store: Store,
    conflictogens: list[Conflictogen],
):
    if message.chat.type != ChatType.PRIVATE:
        # В группе/супергруппе личную статистику не показываем — короткая подсказка.
        await message.answer(_GROUP_STATS_HINT)
        return
    s = store.stats(message.from_user.id)
    await message.answer(_stats_text(s, conflictogens))


@router.callback_query(F.data == CB_MENU_STATS)
async def cb_stats(
    call: CallbackQuery,
    store: Store,
    conflictogens: list[Conflictogen],
):
    # Та же политика, что у /stats: личную статистику не показываем в группах.
    # call.message может быть None (очень старое сообщение) — тогда тоже не показываем.
    if call.message is None or call.message.chat.type != ChatType.PRIVATE:
        await call.answer(_GROUP_STATS_HINT)
        return
    try:
        await safe_edit(
            call,
            _stats_text(store.stats(call.from_user.id), conflictogens),
            main_menu(),
        )
    except Exception:
        await call.answer(ERROR_ANSWER)
        raise
    await call.answer()
