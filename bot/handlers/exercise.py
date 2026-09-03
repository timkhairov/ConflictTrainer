"""Ядро тренажёра: выдача фразы, выбор конфликтогенов, проверка и разбор.

Поток: «Начать тренировку» → фраза + клавиатура выбора → отметки (toggle) →
«Готово» → разбор ответа → «Следующее упражнение» / «В меню».

Данные (conflictogens, exercises, store) передаются в обработчики через
workflow_data диспетчера (см. bot/main.py).
"""
from __future__ import annotations

import random

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery
from aiogram.utils.text_decorations import html_decoration as html

from ..keyboards import (
    CB_MENU_START_TRAINING,
    CB_NEXT,
    CB_SUBMIT,
    CB_TOGGLE,
    exercise_keyboard,
    feedback_keyboard,
)
from ..models import Conflictogen, Exercise
from ..scoring import AttemptResult, evaluate
from ..store import Store
from .common import ERROR_ANSWER, fit_text, safe_edit, safe_edit_markup

router = Router(name="exercise")


class Train(StatesGroup):
    """Состояния тренировки."""

    picking = State()  # ждём, пока пользователь отметит конфликтогены


# --- вспомогательные функции ---


def pick_next(exercises: list[Exercise], store: Store, user_id: int) -> Exercise:
    """Выбирает следующее упражнение: сначала непройденные, потом — по кругу."""
    done = store.completed_ids(user_id)
    remaining = [e for e in exercises if e.id not in done]
    pool = remaining if remaining else list(exercises)
    return random.choice(pool)


def _keyboard_is_stale(call: CallbackQuery, data: dict) -> bool:
    """Нажатая клавиатура не принадлежит сообщению активного упражнения.

    True, если callback пришёл не из того сообщения/чата, в котором выдано
    активное упражнение (например, со «старой» клавиатуры завершённого
    упражнения), или сообщение недоступно — в этом случае нельзя трогать state.
    """
    msg = call.message
    if msg is None or msg.message_id is None or msg.chat is None:
        return True
    return (
        msg.message_id != data.get("message_id")
        or msg.chat.id != data.get("chat_id")
    )


async def _begin(call: CallbackQuery, exercises: list[Exercise], store: Store,
                 conflictogens: list[Conflictogen], state: FSMContext) -> None:
    """Начинает новое упражнение: обновляет сообщение на фразу + клавиатуру."""
    exercise = pick_next(exercises, store, call.from_user.id)
    # Привязываем упражнение к конкретному сообщению: «старые» клавиатуры
    # от предыдущих упражнений перестанут трогать текущее состояние.
    await state.update_data(
        exercise_id=exercise.id,
        selected=[],
        message_id=call.message.message_id,
        chat_id=call.message.chat.id,
    )
    await state.set_state(Train.picking)
    text = (
        f"💬 {html.quote(exercise.phrase)}\n\n"
        "Отметь все конфликтогены, которые ты видишь в этой фразе. "
        "Нажми на пункт, чтобы выбрать/снять выбор."
    )
    try:
        await safe_edit(call, text, exercise_keyboard(conflictogens, set()))
    except Exception:
        await call.answer(ERROR_ANSWER)
        raise
    await call.answer()


def _format_feedback(exercise: Exercise, result: AttemptResult,
                     by_id: dict[str, Conflictogen]) -> str:
    """Собирает текст разбора ответа (HTML)."""
    lines = [
        "💬 <b>Разбор</b>",
        "",
        f"Фраза: {html.quote(exercise.phrase)}",
        "",
    ]

    def render(ids, mark: str, with_desc: bool) -> None:
        for cid in ids:
            cg = by_id.get(cid)
            if not cg:
                continue
            line = f"  {mark} <b>{html.quote(cg.name)}</b>"
            if with_desc and cg.description:
                line += f" — {html.quote(cg.description)}"
            lines.append(line)

    if result.correct:
        lines.append("✅ <b>Верно отметили:</b>")
        render(result.correct, "✓", with_desc=True)
    if result.missed:
        lines.append("")
        lines.append("❌ <b>Пропустили:</b>")
        render(result.missed, "•", with_desc=True)
    if result.false_positive:
        lines.append("")
        lines.append("⚠️ <b>Лишние (здесь он не зашит):</b>")
        for cid in result.false_positive:
            cg = by_id.get(cid)
            lines.append(f"  • {html.quote(cg.name) if cg else html.quote(cid)}")
    if exercise.note:
        lines.append("")
        lines.append(f"📌 {html.quote(exercise.note)}")
    lines.append("")
    if result.perfect:
        lines.append("🎉 Отлично! Все конфликтогены найдены.")
    else:
        lines.append(f"📈 Счёт: <b>{result.score_num} из {result.score_den}</b>")
    return fit_text("\n".join(lines))


# --- обработчики ---


@router.callback_query(F.data == CB_MENU_START_TRAINING)
async def start_training(call: CallbackQuery, exercises: list[Exercise],
                         store: Store, conflictogens: list[Conflictogen],
                         state: FSMContext):
    """Кнопка «Начать тренировку»."""
    await _begin(call, exercises, store, conflictogens, state)


@router.callback_query(F.data == CB_NEXT)
async def next_exercise(call: CallbackQuery, exercises: list[Exercise],
                        store: Store, conflictogens: list[Conflictogen],
                        state: FSMContext):
    """Кнопка «Следующее упражнение»."""
    await _begin(call, exercises, store, conflictogens, state)


@router.callback_query(F.data == CB_SUBMIT)
async def submit(call: CallbackQuery, exercises_by_id: dict[int, Exercise],
                 conflictogens_by_id: dict[str, Conflictogen], store: Store,
                 state: FSMContext):
    """Кнопка «Готово»: проверяем ответ и показываем разбор."""
    data = await state.get_data()
    eid = data.get("exercise_id")
    exercise = exercises_by_id.get(eid) if isinstance(eid, int) else None
    if exercise is None:
        # Активного упражнения нет (например, двойное нажатие «Готово»):
        # только отвечаем на callback и НЕ трогаем сообщение, чтобы не
        # затащить разбор ответа.
        await call.answer("Сначала начни тренировку — нажми «🎯 Начать тренировку» в меню.")
        return
    if _keyboard_is_stale(call, data):
        # «Старая» клавиатура от завершённого упражнения: state и сообщение не трогаем.
        await call.answer("Это упражнение уже завершено — нажми «Следующее упражнение».")
        return

    selected = data.get("selected", [])
    result = evaluate(exercise, selected)
    try:
        store.record_attempt(call.from_user.id, exercise.id, result.score_num, result.score_den)
        await state.clear()
        await safe_edit(call, _format_feedback(exercise, result, conflictogens_by_id),
                        feedback_keyboard())
    except Exception:
        await call.answer(ERROR_ANSWER)
        raise
    await call.answer()


@router.callback_query(F.data.startswith(CB_TOGGLE))
async def toggle(call: CallbackQuery, conflictogens: list[Conflictogen],
                 state: FSMContext):
    """Переключает выбранность одного конфликтогена и перерисовывает клавиатуру."""
    data = await state.get_data()
    if data.get("exercise_id") is None or _keyboard_is_stale(call, data):
        # Нет активного упражнения, или нажата «старая» клавиатура — state не трогаем.
        await call.answer("Это упражнение уже завершено — нажми «Следующее упражнение».")
        return
    cid = call.data[len(CB_TOGGLE):]
    if cid not in {c.id for c in conflictogens}:
        await call.answer("Этот пункт недоступен. Открой новое упражнение.")
        return
    selected = set(data.get("selected", []))
    if cid in selected:
        selected.discard(cid)
    else:
        selected.add(cid)
    try:
        # Сначала перерисовываем, потом фиксируем выбор — при ошибке
        # состояние не остаётся «висящим» относительно видимой клавиатуры.
        await safe_edit_markup(call, exercise_keyboard(conflictogens, selected))
        await state.update_data(selected=list(selected))
    except Exception:
        await call.answer(ERROR_ANSWER)
        raise
    await call.answer()
