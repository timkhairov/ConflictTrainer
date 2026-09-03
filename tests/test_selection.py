"""Тесты выбора следующего упражнения (pick_next в bot/handlers/exercise.py)."""
import random

import pytest

from bot.handlers.exercise import pick_next
from bot.models import Exercise
from bot.store import Store


def _exercises():
    return [Exercise(id=i, phrase=f"p{i}", conflictogens=("a",)) for i in (1, 2, 3)]


def test_unattempted_preferred(tmp_path, monkeypatch):
    exercises = _exercises()
    store = Store(tmp_path / "users.json")
    store.record_attempt(1, 1, 1, 1)  # упражнение 1 уже пройдено

    # детерминированный выбор: всегда первый элемент пула
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    result = pick_next(exercises, store, 1)

    # непройденные (2, 3) должны быть предпочтительны
    assert result.id in (2, 3)
    assert result.id != 1


def test_all_attempted_falls_back_to_full_pool(tmp_path, monkeypatch):
    exercises = _exercises()
    store = Store(tmp_path / "users.json")
    for e in exercises:
        store.record_attempt(1, e.id, 1, 1)  # всё пройдено

    captured = {}

    def fake_choice(seq):
        captured["pool"] = list(seq)
        return seq[0]

    monkeypatch.setattr(random, "choice", fake_choice)
    result = pick_next(exercises, store, 1)

    # при отсутствии непройденных пул — полный список упражнений
    assert captured["pool"] == exercises
    assert result.id in (1, 2, 3)


def test_empty_exercises_raises_indexerror(tmp_path):
    store = Store(tmp_path / "users.json")
    # ПУСТОЙ список → random.choice([]) → IndexError. Зафиксировано текущее
    # поведение (реализация не защищает пустой список); не менять код.
    with pytest.raises(IndexError):
        pick_next([], store, 1)
