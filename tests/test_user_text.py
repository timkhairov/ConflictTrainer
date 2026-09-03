"""Тесты пользовательского текста: без номеров упражнений.

Упражнения выдаются случайно из непройденных, поэтому номер не несёт
смысла и не должен показываться пользователю. Покрыто:
- _phrase_snippet: короткие фразы целиком, длинные — обрезка не длиннее
  лимита по последнему пробелу + «…» только при реальном обрезании,
  HTML-экранирование ПОСЛЕ обрезки (сущности не рвутся);
- _best_lines: фрагмент фразы в «» + счёт, без номера упражнения,
  сортировка по id, повреждённые ключи пропускаются;
- _format_feedback: заголовок «Разбор» без номера, строка «Фраза:»;
- _begin: фраза + инструкция, без заголовка «Упражнение N».
"""
import asyncio
import random
import types

from aiogram.utils.text_decorations import html_decoration as html

from bot.handlers import exercise as ex
from bot.handlers import stats as st
from bot.models import Conflictogen, Exercise
from bot.store import Store


def run(coro):
    return asyncio.run(coro)


# --- _phrase_snippet ---


def test_snippet_short_phrase_unchanged():
    assert st._phrase_snippet("короткая фраза") == "короткая фраза"


def test_snippet_exactly_limit_unchanged():
    phrase = "a" * 40
    assert st._phrase_snippet(phrase) == phrase


def test_snippet_escapes_html_specials():
    assert st._phrase_snippet("a < b > c & d") == "a &lt; b &gt; c &amp; d"


def test_snippet_truncates_at_last_space_with_ellipsis():
    phrase = "a" * 25 + " " + "b" * 25  # 51 > 40
    # обрыв по последнему пробелу: «b…» не попадает в сниппет
    assert st._phrase_snippet(phrase) == "a" * 25 + "…"


def test_snippet_hard_cut_when_no_space():
    phrase = "x" * 50
    assert st._phrase_snippet(phrase) == "x" * 40 + "…"


def test_snippet_escapes_after_truncation_never_splits_entity():
    # Лимит режет фразу в середине; экранируем ПОСЛЕ обрезки, поэтому
    # в результате нет «сырых» спецсимволов и порванных сущностей.
    phrase = "a & b < c> " * 8
    cut = phrase[:40]
    expected = html.quote(cut[: cut.rfind(" ")]) + "…"
    assert st._phrase_snippet(phrase) == expected
    # ни одного «сырого» спецсимвола вне HTML-сущностей
    out = st._phrase_snippet(phrase)
    assert "<" not in out and ">" not in out
    assert "& " not in out


# --- _best_lines ---


def test_best_lines_snippet_score_and_no_number():
    exercises_by_id = {
        1: Exercise(id=1, phrase="короткая фраза", conflictogens=("a", "b")),
        2: Exercise(id=2, phrase="a" * 60, conflictogens=("a",)),
    }
    # порядок в best не важен — вывод сортируется по id
    lines = st._best_lines({"2": 2, "1": 1}, exercises_by_id)
    assert lines == [
        "  • «короткая фраза» — 1/2",
        "  • «" + "a" * 40 + "…» — 2/1",
    ]
    for line in lines:
        assert "Упражнение" not in line


def test_best_lines_skips_bad_keys_and_unknown_ids():
    exercises_by_id = {
        1: Exercise(id=1, phrase="p1", conflictogens=("a",)),
        2: Exercise(id=2, phrase="p2", conflictogens=("a",)),
    }
    best = {"2": 2, "1": 1, "abc": 5, "99": 3}
    lines = st._best_lines(best, exercises_by_id)
    assert len(lines) == 2
    assert lines[0].endswith("1/1")
    assert lines[1].endswith("2/1")


# --- _format_feedback ---


def test_feedback_header_number_free_and_phrase_kept():
    exercise = Exercise(id=7, phrase="твоя фраза", conflictogens=("a",))
    by_id = {"a": Conflictogen(id="a", name="Н", description="деск")}
    result = ex.evaluate(exercise, ["a"])
    text = ex._format_feedback(exercise, result, by_id)
    assert "💬 <b>Разбор</b>" in text
    assert "Упражнение" not in text
    assert "7" not in text
    assert "Фраза: твоя фраза" in text


# --- _begin ---


class FakeState:
    def __init__(self):
        self._data = {}
        self.state = None

    async def update_data(self, **kw):
        self._data.update(kw)

    async def set_state(self, s):
        self.state = s

    async def get_data(self):
        return dict(self._data)


class FakeMessage:
    def __init__(self):
        self.message_id = 111
        self.chat = types.SimpleNamespace(id=5)
        self.edits: list[tuple[str, object]] = []

    async def edit_text(self, text: str, reply_markup=None):
        self.edits.append((text, reply_markup))


class FakeCall:
    def __init__(self):
        self.message = FakeMessage()
        self.from_user = types.SimpleNamespace(id=7)
        self.answered = []

    async def answer(self, *args, **kwargs):
        self.answered.append((args, kwargs))


def test_begin_prompt_number_free(tmp_path, monkeypatch):
    exercises = [Exercise(id=42, phrase="фраза & тест", conflictogens=("a",))]
    store = Store(tmp_path / "users.json")
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    conflictogens = [Conflictogen(id="a", name="Н", description="")]
    call = FakeCall()
    state = FakeState()
    run(ex._begin(call, exercises, store, conflictogens, state))

    text, kb = call.message.edits[0]
    assert text.startswith("💬 фраза &amp; тест")
    assert "Упражнение" not in text
    assert "42" not in text
    assert "Отметь все конфликтогены" in text
    assert kb is not None
    # упражнение зафиксировано в state (внутренний ключ — id)
    assert state._data["exercise_id"] == 42
    assert state.state == ex.Train.picking
