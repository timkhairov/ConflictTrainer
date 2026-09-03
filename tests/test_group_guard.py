"""Охранники групповых чатов: бот не должен отвечать в группах и не должен
протекать личную статистику.

Фиксируется (pin):
- fallback-обработчик сообщений зарегистрирован с фильтром личного чата
  (F.chat.type == ChatType.PRIVATE): в группах/супергруппах/каналах не срабатывает;
- cmd_stats в группе отвечает только подсказкой открыть личный чат,
  а в личном чате — полной статистикой (как раньше);
- cb_stats (кнопка «📊 Мой прогресс») соблюдает ту же политику:
  в группе/супергруппе отвечает только подсказкой без edits и без чтения
  статистики; при call.message is None — тоже только подсказка;
  в личном чате редактирует сообщение полной статистикой.

Проверка фильтров — через HandlerObject.check() (тот же механизм, что у
диспетчера aiogram): filter разрешается против фейкового сообщения, поэтому
тест не зависит от внутренностей MagicFilter.
"""
import asyncio
import types

import pytest

from bot.handlers import fallback, stats as st
from bot.models import Exercise
from bot.store import Store


def run(coro):
    return asyncio.run(coro)


class FakeMessage:
    """Минимальная замена Message: только то, что читают фильтры и обработчики."""

    def __init__(self, chat_type: str, user_id: int = 7):
        self.chat = types.SimpleNamespace(type=chat_type)
        self.from_user = types.SimpleNamespace(id=user_id)
        self.answers: list[str] = []

    async def answer(self, text: str, *args, **kwargs) -> None:
        self.answers.append(text)


class FakeCallbackMessage:
    """Минимальная замена Message внутри CallbackQuery: только edit_text."""

    def __init__(self, chat_type: str):
        self.chat = types.SimpleNamespace(type=chat_type)
        self.edits: list[str] = []

    async def edit_text(self, text: str, *args, **kwargs) -> None:
        self.edits.append(text)


class FakeCallbackQuery:
    """Минимальная замена CallbackQuery: message (или None) + answer()."""

    def __init__(self, chat_type: str | None, user_id: int = 7):
        self.from_user = types.SimpleNamespace(id=user_id)
        self.answers: list[str] = []
        self.message = FakeCallbackMessage(chat_type) if chat_type is not None else None

    async def answer(self, text: str = "", *args, **kwargs) -> None:
        self.answers.append(text)


class _StatsSentinel:
    """Взрывается, если обработчик попытается прочитать личную статистику."""

    def stats(self, user_id: int):
        raise AssertionError("личная статистика не должна читаться вне личного чата")


def _message_handler(router, fn):
    for h in router.message.handlers:
        if h.callback is fn:
            return h
    raise AssertionError(f"обработчик {fn.__name__} не зарегистрирован в {router.name!r}")


# --- fallback: только личный чат ---


def test_fallback_message_filter_passes_private_chat():
    # Фильтр, под которым зарегистрирован fallback, пропускать личный чат…
    h = _message_handler(fallback.router, fallback.fallback_message)
    ok, _ = run(h.check(FakeMessage("private")))
    assert ok is True


@pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel"])
def test_fallback_message_filter_blocks_non_private_chats(chat_type):
    # …а в группах/супергруппах/каналах не срабатывать (бот молчит).
    h = _message_handler(fallback.router, fallback.fallback_message)
    ok, _ = run(h.check(FakeMessage(chat_type)))
    assert ok is False


def test_fallback_callback_still_unfiltered():
    # Callback-фоллбек без изменений: без фильтров (срабатывает на любой callback).
    for h in fallback.router.callback_query.handlers:
        if h.callback is fallback.fallback_callback:
            assert h.filters == []
            return
    raise AssertionError("fallback_callback не зарегистрирован")


# --- cmd_stats: личные данные не в группы ---


def test_cmd_stats_in_group_sends_hint_not_stats(tmp_path):
    store = Store(tmp_path / "users.json")
    store.record_attempt(7, 1, 2, 2)  # у пользователя есть данные — их нельзя протечь
    msg = FakeMessage("group")
    run(st.cmd_stats(msg, store, {}))
    assert len(msg.answers) == 1
    assert "личном чате" in msg.answers[0]
    assert "Твой прогресс" not in msg.answers[0]


def test_cmd_stats_in_supergroup_sends_hint_not_stats(tmp_path):
    store = Store(tmp_path / "users.json")
    store.record_attempt(7, 1, 2, 2)
    msg = FakeMessage("supergroup")
    run(st.cmd_stats(msg, store, {}))
    assert len(msg.answers) == 1
    assert "личном чате" in msg.answers[0]
    assert "Твой прогресс" not in msg.answers[0]


def test_cmd_stats_in_private_shows_full_stats(tmp_path):
    store = Store(tmp_path / "users.json")
    store.record_attempt(7, 1, 2, 2)
    exercises_by_id = {1: Exercise(id=1, phrase="p", conflictogens=("a",))}
    msg = FakeMessage("private")
    run(st.cmd_stats(msg, store, exercises_by_id))
    assert len(msg.answers) == 1
    assert "Твой прогресс" in msg.answers[0]
    assert "2 из 2" in msg.answers[0]


# --- cb_stats (кнопка «📊 Мой прогресс»): та же политика, что у /stats ---


@pytest.mark.parametrize("chat_type", ["group", "supergroup"])
def test_cb_stats_in_group_sends_hint_no_edit_no_store(chat_type):
    # В группе/супергруппе кнопка не редактирует сообщение и не читает store
    # (сентинел взорвался бы иначе), а отвечает ровно одной подсказкой.
    call = FakeCallbackQuery(chat_type)
    run(st.cb_stats(call, _StatsSentinel(), {}))
    assert len(call.answers) == 1
    assert "личном чате" in call.answers[0]
    assert "Твой прогресс" not in call.answers[0]
    assert call.message.edits == []


def test_cb_stats_with_none_message_sends_hint_no_store():
    # call.message is None (очень старое сообщение) — тоже только подсказка,
    # без edits и без чтения store.
    call = FakeCallbackQuery(None)
    run(st.cb_stats(call, _StatsSentinel(), {}))
    assert call.message is None
    assert len(call.answers) == 1
    assert "личном чате" in call.answers[0]


def test_cb_stats_in_private_edits_full_stats(tmp_path):
    # В личном чате кнопка работает как раньше: edit с полной статистикой.
    store = Store(tmp_path / "users.json")
    store.record_attempt(7, 1, 2, 2)
    exercises_by_id = {1: Exercise(id=1, phrase="p", conflictogens=("a",))}
    call = FakeCallbackQuery("private")
    run(st.cb_stats(call, store, exercises_by_id))
    assert len(call.message.edits) == 1
    assert "Твой прогресс" in call.message.edits[0]
    assert "2 из 2" in call.message.edits[0]
    # Успешный сценарий: один ответ без ошибки (не ERROR_ANSWER).
    assert len(call.answers) == 1
    assert "пошло не так" not in call.answers[0]
