"""Ядро тренажёра: выдача фразы, выбор конфликтогенов, проверка и разбор.

Поток: «Начать тренировку» → выбор сферы жизни → пикер тем (отметить
одну/несколько тем, либо «Все темы сферы») → фраза + клавиатура выбора →
отметки (toggle) → «Готово» → разбор ответа →
«Следующее упражнение» (в той же сфере и по тому же набору тем) / «В меню».

Данные (domains, subjects, conflictogens, exercises, store) передаются в
обработчики через workflow_data диспетчера (см. bot/main.py).
"""
from __future__ import annotations

import random

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery
from aiogram.utils.text_decorations import html_decoration as html

from ..keyboards import (
    CB_DOMAIN,
    CB_MENU_START_TRAINING,
    CB_NEXT,
    CB_SUBJECT,
    CB_SUBJECT_ALL,
    CB_SUBJECT_START,
    CB_SUBMIT,
    CB_TO_DOMAINS,
    CB_TOGGLE,
    domain_keyboard,
    exercise_keyboard,
    feedback_keyboard,
    subject_select_keyboard,
)
from ..models import Conflictogen, Domain, Exercise, Subject
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


def _selector_is_stale(call: CallbackQuery, data: dict) -> bool:
    """Нажатая клавиатура не принадлежит сообщению активного пикера тем.

    True, если callback пришёл не из того сообщения/чата, в котором открыт
    пикер тем (например, со «старой» клавиатуры после перехода), или сообщение
    недоступно — в этом случае нельзя трогать state.
    """
    msg = call.message
    if msg is None or msg.message_id is None or msg.chat is None:
        return True
    return (
        msg.message_id != data.get("sel_message_id")
        or msg.chat.id != data.get("sel_chat_id")
    )


async def _begin(call: CallbackQuery, exercises: list[Exercise], store: Store,
                 conflictogens: list[Conflictogen], state: FSMContext,
                 domain_id: str, subject_ids: list[str]) -> None:
    """Начинает новое упражнение: обновляет сообщение на фразу + клавиатуру.

    `exercises` — уже отфильтрованный по сфере и выбранному набору тем список;
    `domain_id` и `subject_ids` запоминаются в состоянии, чтобы «Следующее
    упражнение» продолжало ту же сферу и тот же набор тем. Одновременно
    сбрасываем данные пикера тем (sel_*), так как он закрыт.
    """
    exercise = pick_next(exercises, store, call.from_user.id)
    # Привязываем упражнение к конкретному сообщению: «старые» клавиатуры
    # от предыдущих упражнений перестанут трогать текущее состояние.
    await state.update_data(
        exercise_id=exercise.id,
        selected=[],
        domain_id=domain_id,
        subject_ids=list(subject_ids),
        message_id=call.message.message_id,
        chat_id=call.message.chat.id,
        sel_domain_id=None,
        sel_subjects=[],
        sel_message_id=None,
        sel_chat_id=None,
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
    if not exercise.conflictogens:
        # Контрольный пример: конфликтогенов в фразе нет.
        if result.perfect:
            lines.append("🎉 Верно: в этой фразе нет конфликтогенов.")
        else:
            lines.append("🚫 В этой фразе не было конфликтогенов — отмечать ничего не нужно было.")
    elif result.perfect:
        lines.append("🎉 Отлично! Все конфликтогены найдены.")
    else:
        lines.append(f"📈 Счёт: <b>{result.score_num} из {result.score_den}</b>")
    return fit_text("\n".join(lines))


# --- обработчики ---


@router.callback_query(F.data == CB_MENU_START_TRAINING)
async def choose_domain(call: CallbackQuery, domains: list[Domain],
                        state: FSMContext):
    """Кнопка «Начать тренировку»: показываем выбор сферы жизни."""
    await state.clear()
    try:
        await safe_edit(
            call,
            "Выбери сферу жизни, в которой хочешь потренироваться:",
            domain_keyboard(domains),
        )
    except Exception:
        await call.answer(ERROR_ANSWER)
        raise
    await call.answer()


@router.callback_query(F.data.startswith(CB_DOMAIN))
async def choose_subject(call: CallbackQuery, state: FSMContext,
                         domains_by_id: dict[str, Domain],
                         subjects: list[Subject]):
    """Кнопка сферы жизни: показываем выбор темы внутри этой сферы."""
    dom_id = call.data[len(CB_DOMAIN):]
    domain = domains_by_id.get(dom_id)
    if domain is None:
        # Сфера исчезла из данных, а её кнопка осталась в «старой» клавиатуре.
        await call.answer("Сфера недоступна. Вернись в меню — /start.")
        return
    domain_subjects = [s for s in subjects if s.domain == dom_id]
    if not domain_subjects:
        await call.answer(f"В сфере «{domain.name}» пока нет тем — они скоро появятся.")
        return
    # Фиксируем контекст пикера тем (какая сфера открыта, в каком сообщении),
    # чтобы toggle/старт/назад могли работать и защищаться от «старых» клавиатур.
    await state.update_data(
        sel_domain_id=dom_id,
        sel_subjects=[],
        sel_message_id=call.message.message_id,
        sel_chat_id=call.message.chat.id,
    )
    try:
        await safe_edit(
            call,
            f"Сфера: {html.quote(domain.name)}. "
            "Отметь одну или несколько тем — или выбери все сразу:",
            subject_select_keyboard(domain_subjects, set()),
        )
    except Exception:
        await call.answer(ERROR_ANSWER)
        raise
    await call.answer()


@router.callback_query(F.data.startswith(CB_SUBJECT))
async def toggle_subject(call: CallbackQuery, state: FSMContext,
                         subjects: list[Subject],
                         subjects_by_id: dict[str, Subject]):
    """Кнопка темы в пикере: отмечает/снимает её и перерисовывает отметки.

    Не начинает тренировку — старт идёт кнопками «Начать тренировку»
    (по отмеченным) и «Все темы сферы» (по всем темам).
    """
    data = await state.get_data()
    sel_dom_id = data.get("sel_domain_id")
    if sel_dom_id is None or _selector_is_stale(call, data):
        # Пикер тем закрыт/неактуален, или нажата «старая» клавиатура — state не трогаем.
        await call.answer("Это меню уже неактуально — вернись в меню, /start.")
        return
    sub_id = call.data[len(CB_SUBJECT):]
    subject = subjects_by_id.get(sub_id)
    if subject is None:
        # Тема исчезла из данных, а её кнопка осталась в «старой» клавиатуре.
        await call.answer("Тема недоступна. Вернись в меню — /start.")
        return
    if subject.domain != sel_dom_id:
        # Кнопка темы из другой сферы (например, из «старой» клавиатуры).
        await call.answer("Эта тема из другой сферы — выбери сферу заново.")
        return
    selected = set(data.get("sel_subjects", []))
    if sub_id in selected:
        selected.discard(sub_id)
    else:
        selected.add(sub_id)
    try:
        # Сначала перерисовываем, потом фиксируем выбор — при ошибке
        # состояние не остаётся «висящим» относительно видимой клавиатуры.
        domain_subjects = [s for s in subjects if s.domain == sel_dom_id]
        await safe_edit_markup(call, subject_select_keyboard(domain_subjects, selected))
        await state.update_data(sel_subjects=sorted(selected))
    except Exception:
        await call.answer(ERROR_ANSWER)
        raise
    await call.answer()


@router.callback_query(F.data == CB_SUBJECT_START)
async def start_selected(call: CallbackQuery, state: FSMContext,
                         domains_by_id: dict[str, Domain],
                         subjects: list[Subject],
                         subjects_by_id: dict[str, Subject],
                         exercises: list[Exercise],
                         conflictogens: list[Conflictogen],
                         store: Store):
    """Кнопка «Начать тренировку»: старт по отмеченным темам (нужна хотя бы одна)."""
    data = await state.get_data()
    sel_dom_id = data.get("sel_domain_id")
    if sel_dom_id is None or _selector_is_stale(call, data):
        await call.answer("Это меню уже неактуально — вернись в меню, /start.")
        return
    domain = domains_by_id.get(sel_dom_id)
    if domain is None:
        await call.answer("Сфера недоступна. Вернись в меню — /start.")
        return
    # Оставляем только темы, которые реально существуют и принадлежат этой сфере.
    valid = [
        sid for sid in data.get("sel_subjects", [])
        if (s := subjects_by_id.get(sid)) is not None and s.domain == sel_dom_id
    ]
    if not valid:
        await call.answer("Отметь хотя бы одну тему.")
        return
    pool = [e for e in exercises if e.domain == domain.id and e.subject in valid]
    if not pool:
        # Проверка до pick_next: pick_next([]) падает с IndexError.
        await call.answer("В выбранных темах пока нет упражнений — они скоро появятся.")
        return
    await _begin(call, pool, store, conflictogens, state, domain.id, valid)


@router.callback_query(F.data == CB_SUBJECT_ALL)
async def start_all_subjects(call: CallbackQuery, state: FSMContext,
                             domains_by_id: dict[str, Domain],
                             subjects: list[Subject],
                             exercises: list[Exercise],
                             conflictogens: list[Conflictogen],
                             store: Store):
    """Кнопка «Все темы сферы»: старт по всем темам выбранной сферы в один тап."""
    data = await state.get_data()
    sel_dom_id = data.get("sel_domain_id")
    if sel_dom_id is None or _selector_is_stale(call, data):
        await call.answer("Это меню уже неактуально — вернись в меню, /start.")
        return
    domain = domains_by_id.get(sel_dom_id)
    if domain is None:
        await call.answer("Сфера недоступна. Вернись в меню — /start.")
        return
    pool = [e for e in exercises if e.domain == domain.id]
    if not pool:
        await call.answer(f"В сфере «{domain.name}» пока нет упражнений — они скоро появятся.")
        return
    subject_ids = [s.id for s in subjects if s.domain == domain.id]
    await _begin(call, pool, store, conflictogens, state, domain.id, subject_ids)


@router.callback_query(F.data == CB_TO_DOMAINS)
async def back_to_domains(call: CallbackQuery, domains: list[Domain],
                          state: FSMContext):
    """Кнопка «Назад» в пикере тем: возвращаемся к выбору сферы жизни."""
    await choose_domain(call, domains, state)


@router.callback_query(F.data == CB_NEXT)
async def next_exercise(call: CallbackQuery, exercises: list[Exercise],
                        store: Store, conflictogens: list[Conflictogen],
                        domains: list[Domain], state: FSMContext):
    """Кнопка «Следующее упражнение»: продолжаем в той же сфере и по тому же набору тем."""
    data = await state.get_data()
    dom_id = data.get("domain_id")
    subject_ids = data.get("subject_ids")
    if not dom_id or not subject_ids:
        # Сфера/набор тем не выбраны — предлагаем выбрать заново;
        # без fallback на все упражнения, чтобы не выпрыгивать из выбранного набора.
        await choose_domain(call, domains, state)
        return
    pool = [e for e in exercises if e.domain == dom_id and e.subject in subject_ids]
    if not pool:
        # Выбранные темы опустели (упражнения удалили) — предлагаем выбрать заново.
        await choose_domain(call, domains, state)
        return
    await _begin(call, pool, store, conflictogens, state, dom_id, subject_ids)


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
        store.record_attempt(
            call.from_user.id, exercise.id,
            result.correct, result.missed, result.false_positive,
        )
        # Не сбрасываем состояние целиком: domain_id нужен кнопке «Следующее
        # упражнение», чтобы остаться в той же сфере. Само упражнение считаем
        # закрытым (exercise_id=None) — существующие проверки toggle/submit
        # на «нет активного упражнения» продолжают работать.
        await state.update_data(exercise_id=None, selected=[])
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
