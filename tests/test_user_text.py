"""Тесты пользовательского текста.

Упражнения выдаются случайно из непройденных, поэтому номер не несёт
смысла и не должен показываться пользователю. Покрыто:
- _cg_lines: порядок строк — порядок списка conflictogens (файла данных),
  формат «N из M (P%)», суффикс «лишних» только при fp > 0, строка
  «лишних отметок» для fp без появлений, пропуск не встречавшихся
  конфликтогенов и неизвестных cids из данных, HTML-экранирование имён;
- _stats_text: ранний выход при нулевых попытках, общий раздел без изменений,
  заголовок «По конфликтогенам» только если есть строки;
- _format_feedback: заголовок «Разбор» без номера, строка «Фраза:»;
- _begin: фраза + инструкция, без заголовка «Упражнение N».
"""
import asyncio
import random
import types

from bot.handlers import exercise as ex
from bot.handlers import stats as st
from bot.models import Conflictogen, Exercise
from bot.store import Store


def run(coro):
    return asyncio.run(coro)


def _cgs():
    """Каталог конфликтогенов в «порядке файла данных» (как клавиатура)."""
    return [
        Conflictogen(id="a", name="Генерализация", description=""),
        Conflictogen(id="b", name="Обвинения и стыд", description=""),
        Conflictogen(id="c", name="Оценки", description=""),
        Conflictogen(id="d", name="Не встречался", description=""),
    ]


# --- _cg_lines ---


def test_cg_lines_data_order_and_format():
    # Порядок — по списку conflictogens (a, b), а не по ключам словаря (b, a).
    lines = st._cg_lines(
        {
            "b": {"present": 4, "correct": 3, "false_positive": 1},
            "a": {"present": 8, "correct": 5, "false_positive": 0},
        },
        _cgs(),
    )
    assert lines == [
        f"  • Генерализация — 5 из 8 ({5 / 8 * 100:.0f}%)",
        "  • Обвинения и стыд — 3 из 4 (75%), лишних: 1",
    ]


def test_cg_lines_fp_suffix_only_when_positive():
    # fp == 0 — суффикса «лишних» нет (см. test_cg_lines_data_order_and_format);
    # fp > 0 — добавляется.
    lines = st._cg_lines(
        {"a": {"present": 2, "correct": 1, "false_positive": 2}}, _cgs()
    )
    assert lines == ["  • Генерализация — 1 из 2 (50%), лишних: 2"]


def test_cg_lines_false_positive_only_no_percentage():
    # Появлений не было, но были лишние отметки: строка без процента.
    lines = st._cg_lines(
        {"c": {"present": 0, "correct": 0, "false_positive": 2}}, _cgs()
    )
    assert lines == ["  • Оценки — лишних отметок: 2"]
    assert "%" not in lines[0]


def test_cg_lines_skips_unseen_and_unknown_cids():
    # «d» есть в каталоге, но счётчики нулевые → пропускается;
    # «ghost» есть в данных, но нет в каталоге → тоже не показывается.
    cg = {
        "a": {"present": 1, "correct": 1, "false_positive": 0},
        "d": {"present": 0, "correct": 0, "false_positive": 0},
        "ghost": {"present": 3, "correct": 2, "false_positive": 0},
    }
    lines = st._cg_lines(cg, _cgs())
    assert lines == ["  • Генерализация — 1 из 1 (100%)"]


def test_cg_lines_html_quoting_of_names():
    cgs = [Conflictogen(id="a", name="А <Б> & В", description="")]
    lines = st._cg_lines(
        {"a": {"present": 2, "correct": 1, "false_positive": 0}}, cgs
    )
    assert lines == [f"  • А &lt;Б&gt; &amp; В — 1 из 2 ({1 / 2 * 100:.0f}%)"]


def test_cg_lines_empty_data_no_lines():
    assert st._cg_lines({}, _cgs()) == []


# --- _stats_text ---


def test_stats_text_zero_attempts_early_return():
    s = {
        "attempts": 0, "total_correct": 0, "total_possible": 0,
        "accuracy": None, "completed": [], "conflictogens": {},
    }
    text = st._stats_text(s, _cgs())
    assert "Ты ещё не проходил(а) ни одного упражнения." in text
    assert "По конфликтогенам" not in text


def test_stats_text_totals_unchanged_and_header_when_lines_exist():
    s = {
        "attempts": 3,
        "total_correct": 8,
        "total_possible": 10,
        "accuracy": 0.8,
        "completed": [1, 2],
        "conflictogens": {
            "a": {"present": 8, "correct": 5, "false_positive": 0},
            "b": {"present": 2, "correct": 1, "false_positive": 1},
        },
    }
    text = st._stats_text(s, _cgs())
    # Общий раздел — без изменений.
    assert "📊 <b>Твой прогресс</b>" in text
    assert "Попыток: 3" in text
    assert "Собрано правильных: 8 из 10" in text
    assert "Точность: 80%" in text
    assert "Пройдено упражнений: 2" in text
    # Новый раздел — только с строками.
    assert "🔍 <b>По конфликтогенам:</b>" in text
    assert f"  • Генерализация — 5 из 8 ({5 / 8 * 100:.0f}%)" in text
    assert "  • Обвинения и стыд — 1 из 2 (50%), лишних: 1" in text
    assert "Лучшие счёты" not in text


def test_stats_text_no_header_when_no_conflictogen_lines():
    # Только «ghost» в данных: каталогу он неизвестен → строк нет → заголовка нет.
    s = {
        "attempts": 1, "total_correct": 1, "total_possible": 2,
        "accuracy": 0.5, "completed": [1],
        "conflictogens": {"ghost": {"present": 1, "correct": 1, "false_positive": 0}},
    }
    text = st._stats_text(s, _cgs())
    assert "Попыток: 1" in text
    assert "По конфликтогенам" not in text
    assert "ghost" not in text


def test_stats_text_missing_conflictogens_key():
    # Старая запись без ключа «conflictogens»: не падает, раздела нет.
    s = {
        "attempts": 1, "total_correct": 0, "total_possible": 0,
        "accuracy": None, "completed": [1],
    }
    text = st._stats_text(s, _cgs())
    assert "По конфликтогенам" not in text


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


def test_feedback_clean_perfect():
    # контрольный пример, всё верно (ничего не отмечено)
    exercise = Exercise(id=10, phrase="чистая фраза", conflictogens=(), note="разбор")
    by_id = {"a": Conflictogen(id="a", name="Н", description="деск")}
    result = ex.evaluate(exercise, [])
    text = ex._format_feedback(exercise, result, by_id)
    assert "нет конфликтогенов" in text
    assert "📌 разбор" in text
    assert "Счёт" not in text
    assert "Все конфликтогены найдены" not in text


def test_feedback_clean_false_positives():
    # контрольный пример, но пользователь отметил лишнее
    exercise = Exercise(id=11, phrase="чистая фраза", conflictogens=(), note="")
    by_id = {"a": Conflictogen(id="a", name="Н", description="деск")}
    result = ex.evaluate(exercise, ["a"])
    text = ex._format_feedback(exercise, result, by_id)
    assert "Лишние" in text
    assert "Н" in text
    assert "не было конфликтогенов" in text
    assert "0 из 0" not in text


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
