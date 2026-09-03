"""Тесты оценки ответа (bot/scoring.py).

Важно: порядок в `correct` и `missed` следует ПОРЯДКУ УПРАЖНЕНИЯ
(exercise.conflictogens), а `false_positive` — порядку выбора пользователя.
Это соответствует реализации в bot/scoring.py.
"""
from bot.models import Exercise
from bot.scoring import evaluate


def _exercise():
    return Exercise(id=1, phrase="p", conflictogens=("a", "b", "c"), note="")


def test_full_selection_perfect():
    e = _exercise()
    r = evaluate(e, ["a", "b", "c"])
    assert r.perfect
    assert r.score_num == 3
    assert r.score_den == 3
    assert r.correct == ("a", "b", "c")
    assert r.missed == ()
    assert r.false_positive == ()


def test_empty_selection_all_missed():
    e = _exercise()
    r = evaluate(e, [])
    assert not r.perfect
    assert r.score_num == 0
    assert r.score_den == 3
    assert r.correct == ()
    # missed — все конфликтогены, в порядке упражнения
    assert r.missed == ("a", "b", "c")
    assert r.false_positive == ()


def test_partial_selection_ordering():
    e = _exercise()  # correct set: a, b, c
    # выбраны c и a (в порядке выбора c, a); b пропущен
    r = evaluate(e, ["c", "a"])
    # correct идёт в порядке УПРАЖНЕНИЯ (a, c), а не порядка выбора (c, a)
    assert r.correct == ("a", "c")
    assert r.missed == ("b",)
    assert r.false_positive == ()
    assert r.score_num == 2
    assert r.score_den == 3
    assert not r.perfect


def test_false_positives():
    e = Exercise(id=2, phrase="p", conflictogens=("a", "b"), note="")
    r = evaluate(e, ["b", "zzz", "yyy"])
    assert "zzz" in r.false_positive
    assert "yyy" in r.false_positive
    assert "zzz" not in r.correct
    assert r.correct == ("b",)
    assert r.missed == ("a",)
    assert r.false_positive == ("zzz", "yyy")  # порядок выбора
    assert r.score_num == 1
    assert r.score_den == 2
    assert not r.perfect


def test_mixed_case_scores():
    e = Exercise(id=3, phrase="p", conflictogens=("a", "b", "c", "d"), note="")
    r = evaluate(e, ["a", "c", "x"])
    assert r.correct == ("a", "c")
    assert r.missed == ("b", "d")
    assert r.false_positive == ("x",)
    assert r.score_num == 2
    assert r.score_den == 4
    assert r.exercise_id == 3
    assert not r.perfect
