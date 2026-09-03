"""Тесты загрузки и валидации данных (bot/data_loader.py).

Валидация проверяется на синтетических файлах в tmp_path: записываем корректную
базовую структуру и мутируем конкретное поле. Обязательные текстовые поля
(name/phrase) должны присутствовать как непустые строки; необязательные
(description/note) — опциональные: отсутствующий ключ или JSON null дают "",
присутствующее значение обязано быть строкой (bool/числа отклоняются).
"""
import json

import pytest

from bot.config import DATA_DIR
from bot.data_loader import (
    DataError,
    load_all,
    load_conflictogens,
    load_exercises,
)


def _write(path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _load_conf(tmp_path, items):
    p = tmp_path / "conflictogens.json"
    _write(p, {"conflictogens": items})
    return load_conflictogens(p)


def _load_ex(tmp_path, items, known):
    p = tmp_path / "exercises.json"
    _write(p, {"exercises": items})
    return load_exercises(p, set(known))


# --- реальная библиотека данных ---


def test_load_all_real_data():
    conflictogens, exercises = load_all(DATA_DIR)
    assert len(conflictogens) == 7
    assert len(exercises) == 88
    assert [e.id for e in exercises] == list(range(1, 89))
    assert exercises[-1].conflictogens == ()  # контрольный пример
    ids = {c.id for c in conflictogens}
    for e in exercises:
        for cid in e.conflictogens:
            assert cid in ids, f"unknown conflictogen {cid} in exercise {e.id}"


# --- conflictogens: отклонения ---


def test_conflictogen_missing_name_rejected(tmp_path):
    # «missing required field»: name обязателен (allow_empty=False)
    with pytest.raises(DataError):
        _load_conf(tmp_path, [{"id": "a"}])


def test_conflictogen_name_as_bool_rejected(tmp_path):
    # текстовое поле bool → отклоняется
    with pytest.raises(DataError):
        _load_conf(tmp_path, [{"id": "a", "name": True, "description": ""}])


def test_conflictogen_id_bool_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_conf(tmp_path, [{"id": True, "name": "A", "description": ""}])


def test_conflictogen_id_int_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_conf(tmp_path, [{"id": 1, "name": "A", "description": ""}])


def test_conflictogen_id_float_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_conf(tmp_path, [{"id": 1.5, "name": "A", "description": ""}])


def test_conflictogen_duplicate_id_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_conf(tmp_path, [
            {"id": "a", "name": "A", "description": ""},
            {"id": "a", "name": "B", "description": ""},
        ])


def test_conflictogen_empty_list_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_conf(tmp_path, [])


def test_conflictogen_non_dict_top_level_rejected(tmp_path):
    p = tmp_path / "conflictogens.json"
    _write(p, [1, 2, 3])  # список на верхнем уровне, а не объект
    with pytest.raises(DataError):
        load_conflictogens(p)


def test_conflictogen_missing_file_rejected(tmp_path):
    with pytest.raises(DataError):
        load_conflictogens(tmp_path / "nope.json")


# --- conflictogens: границы длины ---


def test_conflictogen_id_payload_64_bytes_accepted(tmp_path):
    # "cg:" (3 байта) + 61 = 64 байта → в пределах лимита
    cid = "a" * 61
    assert len(("cg:" + cid).encode("utf-8")) == 64
    result = _load_conf(tmp_path, [{"id": cid, "name": "A", "description": ""}])
    assert len(result) == 1
    assert result[0].id == cid


def test_conflictogen_id_payload_65_bytes_rejected(tmp_path):
    # 3 + 62 = 65 байт → превышает лимит Telegram
    cid = "a" * 62
    assert len(("cg:" + cid).encode("utf-8")) == 65
    with pytest.raises(DataError):
        _load_conf(tmp_path, [{"id": cid, "name": "A", "description": ""}])


def test_conflictogen_name_62_accepted(tmp_path):
    result = _load_conf(tmp_path, [{"id": "a", "name": "x" * 62, "description": ""}])
    assert len(result[0].name) == 62


def test_conflictogen_name_63_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_conf(tmp_path, [{"id": "a", "name": "x" * 63, "description": ""}])


def test_conflictogen_description_500_accepted(tmp_path):
    result = _load_conf(tmp_path, [{"id": "a", "name": "A", "description": "d" * 500}])
    assert len(result[0].description) == 500


def test_conflictogen_description_501_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_conf(tmp_path, [{"id": "a", "name": "A", "description": "d" * 501}])


def test_conflictogen_description_as_bool_rejected(tmp_path):
    # текстовое поле description bool → отклоняется
    with pytest.raises(DataError):
        _load_conf(tmp_path, [{"id": "a", "name": "A", "description": True}])


def test_conflictogen_missing_description_defaults_to_empty(tmp_path):
    # description — необязательное поле: отсутствующий ключ → "" (см. README и
    # дефолт Conflictogen.description = ""), бот не должен падать на таких данных.
    result = _load_conf(tmp_path, [{"id": "a", "name": "A"}])
    assert len(result) == 1
    assert result[0].description == ""


def test_conflictogen_null_description_defaults_to_empty(tmp_path):
    # JSON null эквивалентен отсутствию ключа → ""
    result = _load_conf(tmp_path, [{"id": "a", "name": "A", "description": None}])
    assert result[0].description == ""


# --- exercises: отклонения ---


def test_exercise_duplicate_id_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "note": ""},
            {"id": 1, "phrase": "y", "conflictogens": ["b"], "note": ""},
        ], {"a", "b"})


def test_exercise_unknown_conflictogen_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["zzz"], "note": ""},
        ], {"a", "b"})


def test_exercise_empty_list_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [], {"a", "b"})


def test_exercise_empty_conflictogens_accepted(tmp_path):
    # пустой список conflictogens — контрольный пример (фразы без конфликтогенов)
    result = _load_ex(tmp_path, [{"id": 1, "phrase": "x", "conflictogens": []}], {"a", "b"})
    assert len(result) == 1
    assert result[0].conflictogens == ()


def test_exercise_missing_conflictogens_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [{"id": 1, "phrase": "x"}], {"a", "b"})


def test_exercise_conflictogens_non_list_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [{"id": 1, "phrase": "x", "conflictogens": "a"}], {"a", "b"})


def test_exercise_id_float_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [{"id": 1.5, "phrase": "x", "conflictogens": ["a"], "note": ""}], {"a", "b"})


def test_exercise_id_bool_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [{"id": True, "phrase": "x", "conflictogens": ["a"], "note": ""}], {"a", "b"})


def test_exercise_id_string_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [{"id": "1", "phrase": "x", "conflictogens": ["a"], "note": ""}], {"a", "b"})


def test_exercise_id_missing_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [{"phrase": "x", "conflictogens": ["a"], "note": ""}], {"a", "b"})


def test_exercise_missing_phrase_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [{"id": 1, "conflictogens": ["a"], "note": ""}], {"a", "b"})


def test_exercise_phrase_as_bool_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [{"id": 1, "phrase": True, "conflictogens": ["a"], "note": ""}], {"a", "b"})


def test_exercise_note_as_bool_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [{"id": 1, "phrase": "x", "conflictogens": ["a"], "note": True}], {"a", "b"})


def test_exercise_missing_note_defaults_to_empty(tmp_path):
    # note — необязательное поле (README: «необязательное пояснение к разбору»,
    # дефолт Exercise.note = ""): отсутствие ключа не должно ломать загрузку.
    result = _load_ex(tmp_path, [{"id": 1, "phrase": "x", "conflictogens": ["a"]}], {"a", "b"})
    assert len(result) == 1
    assert result[0].note == ""


def test_exercise_null_note_defaults_to_empty(tmp_path):
    # JSON null эквивалентен отсутствию ключа → ""
    result = _load_ex(
        tmp_path, [{"id": 1, "phrase": "x", "conflictogens": ["a"], "note": None}], {"a", "b"}
    )
    assert result[0].note == ""


# --- exercises: границы длины ---


def test_exercise_phrase_1500_accepted(tmp_path):
    result = _load_ex(tmp_path, [
        {"id": 1, "phrase": "p" * 1500, "conflictogens": ["a"], "note": ""},
    ], {"a", "b"})
    assert len(result[0].phrase) == 1500


def test_exercise_phrase_1501_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "p" * 1501, "conflictogens": ["a"], "note": ""},
        ], {"a", "b"})


def test_exercise_note_1000_accepted(tmp_path):
    result = _load_ex(tmp_path, [
        {"id": 1, "phrase": "x", "conflictogens": ["a"], "note": "n" * 1000},
    ], {"a", "b"})
    assert len(result[0].note) == 1000


def test_exercise_note_1001_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "note": "n" * 1001},
        ], {"a", "b"})
