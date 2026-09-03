"""Тесты общих помощников (bot/handlers/common.py): fit_text и safe_edit*."""
import asyncio

import pytest
from aiogram.exceptions import TelegramBadRequest

from bot.handlers import common


def run(coro):
    return asyncio.run(coro)


def _tb(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(method="editMessageText", message=message)


class _FakeMessage:
    def __init__(self, exc: TelegramBadRequest | None = None):
        self._exc = exc
        self.calls = []

    async def edit_text(self, text, reply_markup=None):
        self.calls.append(("edit_text", text, reply_markup))
        if self._exc is not None:
            raise self._exc

    async def edit_reply_markup(self, reply_markup=None):
        self.calls.append(("edit_reply_markup", reply_markup))
        if self._exc is not None:
            raise self._exc


class _FakeCall:
    def __init__(self, message):
        self.message = message


# --- fit_text ---


def test_fit_text_short_unchanged():
    assert common.fit_text("hello", 100) == "hello"


def test_fit_text_exactly_limit_unchanged():
    # текст ровно лимита возвращается без изменений (без «…»)
    t = "a" * 100
    assert common.fit_text(t, 100) == t


def test_fit_text_over_limit_truncated():
    r = common.fit_text("a" * 110, 100)
    assert len(r) <= 100
    assert r.endswith("…")


def test_fit_text_no_dangling_tag():
    # режем так, чтобы не остаться внутри тега «<b>…»
    r = common.fit_text("a" * 47 + "<b>x", 50)
    assert len(r) <= 50
    assert r.endswith("…")
    assert r.count("<") == 0


def test_fit_text_no_dangling_entity():
    # не обрываем HTML-сущность вида «&am…»
    r = common.fit_text("a" * 48 + "&amp;x", 50)
    assert len(r) <= 50
    assert r.endswith("…")
    assert r.count("&") == 0


def test_fit_text_real_limit_4096():
    assert common.fit_text("a" * 4096) == "a" * 4096  # ровно лимит — без изменений
    r = common.fit_text("a" * 4097)
    assert len(r) <= 4096
    assert r.endswith("…")


# --- safe_edit ---


def test_safe_edit_not_modified_swallowed():
    msg = _FakeMessage(exc=_tb("Bad Request: message is not modified"))
    call = _FakeCall(msg)
    run(common.safe_edit(call, "text", None))  # не должно выбрасывать
    assert msg.calls  # edit_text действительно вызывался


def test_safe_edit_not_found_swallowed():
    msg = _FakeMessage(exc=_tb("Bad Request: message to edit not found"))
    call = _FakeCall(msg)
    run(common.safe_edit(call, "text", None))


def test_safe_edit_other_propagates():
    msg = _FakeMessage(exc=_tb("Bad Request: some other error"))
    call = _FakeCall(msg)
    with pytest.raises(TelegramBadRequest):
        run(common.safe_edit(call, "text", None))


# --- safe_edit_markup ---


def test_safe_edit_markup_not_modified_swallowed():
    msg = _FakeMessage(exc=_tb("Bad Request: message is not modified"))
    call = _FakeCall(msg)
    run(common.safe_edit_markup(call, None))


def test_safe_edit_markup_not_found_swallowed():
    msg = _FakeMessage(exc=_tb("Bad Request: message to edit not found"))
    call = _FakeCall(msg)
    run(common.safe_edit_markup(call, None))


def test_safe_edit_markup_other_propagates():
    msg = _FakeMessage(exc=_tb("Bad Request: some other error"))
    call = _FakeCall(msg)
    with pytest.raises(TelegramBadRequest):
        run(common.safe_edit_markup(call, None))
