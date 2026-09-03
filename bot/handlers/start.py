"""Стартовые команды, главное меню и справка «что такое конфликтоген»."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.text_decorations import html_decoration as html

from ..keyboards import CB_MENU_ABOUT, CB_TO_MENU, main_menu
from ..models import Conflictogen
from .common import ERROR_ANSWER, fit_text, safe_edit

router = Router(name="start")

WELCOME = (
    "👋 Привет! Я — тренажёр распознавания конфликтогенов.\n\n"
    "Я показываю конфликтную ситуацию (фразу), а ты отмечаешь все "
    "конфликтогены — паттерны деструктивной обратной связи, «зашитые» в "
    "эту ситуацию. После этого я проверяю ответ и объясняю, что было верно, "
    "а что стоит доработать.\n\n"
    "Выбери, что сделать:"
)


def _about_text(conflictogens: list[Conflictogen]) -> str:
    lines = [
        "ℹ️ <b>Что такое конфликтоген?</b>",
        "",
        "Конфликтоген — это паттерн деструктивной обратной связи: приём "
        "общения, «зашитый» в слова. Он незаметен в отдельности, но именно "
        "такие паттерны разгоняют конфликт.",
        "",
        "Твоя задача — по фразе находить такие паттерны. Сейчас в тренировке "
        "участвуют:",
        "",
    ]
    for cg in conflictogens:
        lines.append(f"• <b>{html.quote(cg.name)}</b>" + (f" — {html.quote(cg.description)}" if cg.description else ""))
    return fit_text("\n".join(lines))


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Команда /start — приветствие и главное меню."""
    await message.answer(WELCOME, reply_markup=main_menu())


@router.callback_query(F.data == CB_TO_MENU)
async def to_menu(call: CallbackQuery, state: FSMContext):
    """Возврат в главное меню (сбрасывает состояние тренировки)."""
    try:
        await state.clear()
        await safe_edit(call, WELCOME, main_menu())
    except Exception:
        await call.answer(ERROR_ANSWER)
        raise
    await call.answer()


@router.callback_query(F.data == CB_MENU_ABOUT)
async def about(call: CallbackQuery, conflictogens: list[Conflictogen]):
    """Справка: определение + список конфликтогенов."""
    try:
        await safe_edit(call, _about_text(conflictogens), main_menu())
    except Exception:
        await call.answer(ERROR_ANSWER)
        raise
    await call.answer()
