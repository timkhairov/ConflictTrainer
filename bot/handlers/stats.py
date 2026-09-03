"""Статистика прогресса пользователя."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.text_decorations import html_decoration as html

from ..keyboards import CB_MENU_STATS, main_menu
from ..models import Exercise
from ..store import Store
from .common import ERROR_ANSWER, fit_text, safe_edit

router = Router(name="stats")

# Статистика — личные данные: в группах показываем только подсказку.
_GROUP_STATS_HINT = "📊 Статистику показываю только в личном чате — напиши мне «/stats» в личке."


def _phrase_snippet(phrase: str, limit: int = 40) -> str:
    """HTML-безопасный короткий фрагмент фразы для строки статистики.

    Фраза короче лимита — целиком, без «…». Длинная — обрезается не более
    чем до `limit` символов: обрываем по последнему пробелу (чтобы не рвать
    слово), «…» добавляем только если обрезание реально произошло.
    Экранируем html.quote ПОСЛЕ обрезки: нельзя обрезать уже экранированный
    текст — можно разрезать HTML-сущность (например, «&am…»).
    """
    if len(phrase) <= limit:
        return html.quote(phrase)
    cut = phrase[:limit]
    space = cut.rfind(" ")
    if space > 0:
        cut = cut[:space]
    return html.quote(cut.rstrip()) + "…"


def _best_lines(best: dict[str, int], exercises_by_id: dict[int, Exercise]) -> list[str]:
    """По одной строке на упражнение: фрагмент фразы и лучший счёт.

    Порядок — по возрастанию id (стабильный список). Ключи, которые не
    сводятся к целому id или не совпадают ни с одним упражнением, пропускаются
    молча (защита от повреждённых записей).
    """
    lines: list[tuple[int, str]] = []
    for key, score in best.items():
        try:
            eid = int(key)
        except (TypeError, ValueError):
            continue
        exercise = exercises_by_id.get(eid)
        if exercise is None:
            continue
        snippet = _phrase_snippet(exercise.phrase)
        lines.append((eid, f"  • «{snippet}» — {score}/{len(exercise.conflictogens)}"))
    lines.sort(key=lambda item: item[0])
    return [line for _, line in lines]


def _stats_text(s: dict, exercises_by_id: dict[int, Exercise]) -> str:
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
    best = s.get("best") or {}
    if best:
        lines = _best_lines(best, exercises_by_id)
        if lines:
            text += "\n\n🏆 <b>Лучшие счёты:</b>\n" + "\n".join(lines)
    # Гарантируем, что текст не превысит лимит Telegram (4096).
    return fit_text(text)


@router.message(Command("stats"))
async def cmd_stats(
    message: Message,
    store: Store,
    exercises_by_id: dict[int, Exercise],
):
    if message.chat.type != ChatType.PRIVATE:
        # В группе/супергруппе личную статистику не показываем — короткая подсказка.
        await message.answer(_GROUP_STATS_HINT)
        return
    s = store.stats(message.from_user.id)
    await message.answer(_stats_text(s, exercises_by_id))


@router.callback_query(F.data == CB_MENU_STATS)
async def cb_stats(
    call: CallbackQuery,
    store: Store,
    exercises_by_id: dict[int, Exercise],
):
    # Та же политика, что у /stats: личную статистику не показываем в группах.
    # call.message может быть None (очень старое сообщение) — тогда тоже не показываем.
    if call.message is None or call.message.chat.type != ChatType.PRIVATE:
        await call.answer(_GROUP_STATS_HINT)
        return
    try:
        await safe_edit(
            call,
            _stats_text(store.stats(call.from_user.id), exercises_by_id),
            main_menu(),
        )
    except Exception:
        await call.answer(ERROR_ANSWER)
        raise
    await call.answer()
