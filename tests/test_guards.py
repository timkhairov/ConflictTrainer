"""Тесты «охранников» (guards) и обработчиков toggle/submit/cb_stats.

Покрыто:
- _keyboard_is_stale (привязка клавиатуры к сообщению/чату);
- submit: нет активного упражнения / устаревшая клавиатура → только тост;
- toggle: неизвестный id / вкл / выкл / устаревшая клавиатура;
- cb_stats: «not modified» глотается, другая ошибка → ERROR_ANSWER + re-raise.
"""
import asyncio
import types

import pytest
from aiogram.exceptions import TelegramBadRequest

from bot.handlers import exercise as ex
from bot.handlers import stats as st
from bot.models import Conflictogen, Exercise
from bot.store import Store


def run(coro):
    return asyncio.run(coro)


class FakeState:
    def __init__(self, data=None):
        self._data = dict(data or {})
        self.updates = []
        self.cleared = 0

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kw):
        self._data.update(kw)
        self.updates.append(kw)

    async def clear(self):
        self.cleared += 1


class FakeMessage:
    def __init__(self, message_id=111, chat_id=5, exc: TelegramBadRequest | None = None):
        self.message_id = message_id
        self.chat = types.SimpleNamespace(id=chat_id, type="private")
        self._exc = exc
        self.edit_calls = []

    async def edit_text(self, text, reply_markup=None):
        self.edit_calls.append(("edit_text", text, reply_markup))
        if self._exc is not None:
            raise self._exc

    async def edit_reply_markup(self, reply_markup=None):
        self.edit_calls.append(("edit_reply_markup", reply_markup))
        if self._exc is not None:
            raise self._exc


class FakeCall:
    def __init__(self, message=None, data="cg:respect", from_user_id=1):
        self.message = message
        self.data = data
        self.from_user = types.SimpleNamespace(id=from_user_id)
        self.answered = []

    async def answer(self, *args, **kwargs):
        self.answered.append((args, kwargs))


def _conflictogens():
    return [
        Conflictogen(id="respect", name="R", description=""),
        Conflictogen(id="autonomy", name="A", description=""),
    ]


# --- _keyboard_is_stale ---


def test_keyboard_stale_message_none():
    call = FakeCall(message=None)
    assert ex._keyboard_is_stale(call, {"message_id": 1, "chat_id": 5}) is True


def test_keyboard_stale_message_id_mismatch():
    call = FakeCall(message=FakeMessage(message_id=111, chat_id=5))
    assert ex._keyboard_is_stale(call, {"message_id": 222, "chat_id": 5}) is True


def test_keyboard_stale_chat_mismatch():
    call = FakeCall(message=FakeMessage(message_id=111, chat_id=5))
    assert ex._keyboard_is_stale(call, {"message_id": 111, "chat_id": 6}) is True


def test_keyboard_not_stale_when_matching():
    call = FakeCall(message=FakeMessage(message_id=111, chat_id=5))
    assert ex._keyboard_is_stale(call, {"message_id": 111, "chat_id": 5}) is False


# --- submit ---


def test_submit_no_active_exercise(tmp_path):
    store = Store(tmp_path / "users.json")
    call = FakeCall(message=FakeMessage())
    state = FakeState({})  # нет exercise_id
    run(ex.submit(call, {}, {}, store, state))
    assert len(call.answered) == 1
    assert state.cleared == 0
    assert state.updates == []
    assert call.message.edit_calls == []


def test_submit_stale_keyboard(tmp_path):
    store = Store(tmp_path / "users.json")
    exercise = Exercise(id=1, phrase="p", conflictogens=("a",))
    exercises_by_id = {1: exercise}
    # message_id в message (999) != message_id в state (111) → устаревшая
    call = FakeCall(message=FakeMessage(message_id=999, chat_id=5))
    state = FakeState({"exercise_id": 1, "selected": ["a"], "message_id": 111, "chat_id": 5})
    run(ex.submit(call, exercises_by_id, {}, store, state))
    assert len(call.answered) == 1
    assert state.cleared == 0
    assert call.message.edit_calls == []
    assert store.completed_ids(1) == set()  # record_attempt не вызывался


# --- toggle ---


def test_toggle_unknown_id(tmp_path):
    call = FakeCall(message=FakeMessage(message_id=111, chat_id=5), data="cg:ghost")
    state = FakeState({"exercise_id": 1, "selected": [], "message_id": 111, "chat_id": 5})
    run(ex.toggle(call, _conflictogens(), state))
    assert len(call.answered) == 1
    assert state.updates == []           # state не менялся
    assert call.message.edit_calls == []  # перерисовки нет


def test_toggle_valid_on(tmp_path):
    call = FakeCall(message=FakeMessage(message_id=111, chat_id=5), data="cg:respect")
    state = FakeState({"exercise_id": 1, "selected": [], "message_id": 111, "chat_id": 5})
    run(ex.toggle(call, _conflictogens(), state))
    assert len(call.message.edit_calls) == 1  # перерисовка
    assert state.updates and state.updates[-1]["selected"] == ["respect"]
    assert len(call.answered) == 1


def test_toggle_valid_off(tmp_path):
    call = FakeCall(message=FakeMessage(message_id=111, chat_id=5), data="cg:respect")
    state = FakeState({"exercise_id": 1, "selected": ["respect"], "message_id": 111, "chat_id": 5})
    run(ex.toggle(call, _conflictogens(), state))
    assert len(call.message.edit_calls) == 1
    assert state.updates and state.updates[-1]["selected"] == []
    assert len(call.answered) == 1


def test_toggle_stale_keyboard(tmp_path):
    call = FakeCall(message=FakeMessage(message_id=999, chat_id=5), data="cg:respect")
    state = FakeState({"exercise_id": 1, "selected": [], "message_id": 111, "chat_id": 5})
    run(ex.toggle(call, _conflictogens(), state))
    assert len(call.answered) == 1
    assert state.updates == []
    assert call.message.edit_calls == []


# --- cb_stats (stats.py) ---


def test_cb_stats_not_modified_swallowed_and_answered(tmp_path):
    store = Store(tmp_path / "users.json")
    msg = FakeMessage(
        message_id=1, chat_id=5,
        exc=TelegramBadRequest(method="editMessageText",
                               message="Bad Request: message is not modified"),
    )
    call = FakeCall(message=msg, data="menu:stats")
    run(st.cb_stats(call, store, {}))  # не должно выбрасывать
    assert len(call.answered) == 1


def test_cb_stats_other_error_answered_and_re_raised(tmp_path):
    store = Store(tmp_path / "users.json")
    msg = FakeMessage(
        message_id=1, chat_id=5,
        exc=TelegramBadRequest(method="editMessageText",
                               message="Bad Request: some other error"),
    )
    call = FakeCall(message=msg, data="menu:stats")
    with pytest.raises(TelegramBadRequest):
        run(st.cb_stats(call, store, {}))
    # текущее поведение: перед re-raise отвечает ERROR_ANSWER ровно один раз
    assert len(call.answered) == 1
