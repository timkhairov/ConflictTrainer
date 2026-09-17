"""Тесты хранилища прогресса (bot/store.py).

Покрыты: поведение при отсутствии файла, накопление общей статистики и
счётчиков по конфликтогенам, quarantine повреждённых файлов (невалидный JSON
/ не-UTF-8 / не-объект), нормализация битых записей (включая «conflictogens»
и бесконечности),
копирование результата stats() и персистентность.
"""
import json

from bot.store import Store, _coerce_int


def _path(tmp_path):
    return tmp_path / "users.json"


# --- отсутствие файла = первый запуск ---


def test_missing_file_returns_defaults(tmp_path):
    s = Store(_path(tmp_path))
    st = s.stats(1)
    assert st["attempts"] == 0
    assert st["total_correct"] == 0
    assert st["total_possible"] == 0
    assert st["accuracy"] is None
    assert st["completed"] == []
    assert st["conflictogens"] == {}
    assert "best" not in st  # поле «best» удалено
    assert s.completed_ids(1) == set()


def test_missing_file_first_record_creates_file(tmp_path):
    p = _path(tmp_path)
    assert not p.exists()
    s = Store(p)
    s.record_attempt(1, 1, ("a",), (), ())
    assert p.exists()


# --- накопление общей статистики ---


def test_record_attempt_increments_and_accumulates(tmp_path):
    s = Store(_path(tmp_path))
    s.record_attempt(1, 1, ("a", "b"), ("c",), ("d",))
    s.record_attempt(1, 1, ("a",), ("b", "c"), ("d", "e"))  # слабее, то же упражнение
    st = s.stats(1)
    assert st["attempts"] == 2
    assert st["total_correct"] == 3  # 2 + 1
    assert st["total_possible"] == 6  # (2+1) + (1+2)
    assert st["completed"] == [1]  # дедупликация


def test_completed_dedupes(tmp_path):
    s = Store(_path(tmp_path))
    s.record_attempt(1, 7, ("a",), (), ())
    s.record_attempt(1, 7, ("a",), (), ())
    s.record_attempt(1, 8, ("a",), (), ())
    assert s.completed_ids(1) == {7, 8}


def test_stats_accuracy_none_when_no_possible(tmp_path):
    s = Store(_path(tmp_path))
    assert s.stats(1)["accuracy"] is None


def test_stats_accuracy_ratio(tmp_path):
    s = Store(_path(tmp_path))
    s.record_attempt(1, 1, ("a", "b"), ("c",), ())
    assert s.stats(1)["accuracy"] == 2 / 3


# --- счётчики по конфликтогенам ---


def test_record_attempt_per_conflictogen_counters(tmp_path):
    # Каждый id попадает в свой счётчик; present = correct + missed.
    s = Store(_path(tmp_path))
    s.record_attempt(1, 1, ("a", "b"), ("c",), ("d",))
    s.record_attempt(1, 2, ("a",), ("d",), ("b",))
    cg = s.stats(1)["conflictogens"]
    assert cg["a"] == {"present": 2, "correct": 2, "false_positive": 0}
    assert cg["b"] == {"present": 1, "correct": 1, "false_positive": 1}
    assert cg["c"] == {"present": 1, "correct": 0, "false_positive": 0}
    assert cg["d"] == {"present": 1, "correct": 0, "false_positive": 1}
    assert set(cg) == {"a", "b", "c", "d"}


def test_record_attempt_control_example_only_false_positive(tmp_path):
    # Контрольный пример (0/0): попытка фиксируется, конфликтогены попадают
    # только в «лишние отметки», а не в «появился/найден».
    s = Store(_path(tmp_path))
    s.record_attempt(1, 42, (), (), ("a",))
    s.record_attempt(1, 42, (), (), ("a", "b"))
    st = s.stats(1)
    assert st["attempts"] == 2
    assert st["total_correct"] == 0
    assert st["total_possible"] == 0
    assert st["accuracy"] is None
    assert st["completed"] == [42]
    assert st["conflictogens"] == {
        "a": {"present": 0, "correct": 0, "false_positive": 2},
        "b": {"present": 0, "correct": 0, "false_positive": 1},
    }


def test_record_attempt_accepts_lists(tmp_path):
    # Аргументы принимают и списки (обёртка материализует их в кортежи).
    s = Store(_path(tmp_path))
    s.record_attempt(1, 1, ["a"], ["b"], ["c"])
    st = s.stats(1)
    assert st["conflictogens"]["a"] == {"present": 1, "correct": 1, "false_positive": 0}
    assert st["conflictogens"]["b"] == {"present": 1, "correct": 0, "false_positive": 0}
    assert st["conflictogens"]["c"] == {"present": 0, "correct": 0, "false_positive": 1}


# --- stats() возвращает копию ---


def test_stats_returns_copy(tmp_path):
    s = Store(_path(tmp_path))
    s.record_attempt(1, 1, ("a",), (), ())
    st = s.stats(1)
    # Мутация результата не должна трогать внутреннее состояние хранилища.
    st["attempts"] = 999
    st["conflictogens"]["a"]["correct"] = 999
    st["conflictogens"]["a"]["injected"] = 1
    st2 = s.stats(1)
    assert st2["attempts"] == 1
    assert st2["conflictogens"]["a"] == {"present": 1, "correct": 1, "false_positive": 0}
    assert "injected" not in st2["conflictogens"]["a"]


# --- quarantine повреждённых файлов ---


def test_quarantine_invalid_json(tmp_path):
    p = _path(tmp_path)
    p.write_text("{not valid json", encoding="utf-8")
    s = Store(p)
    assert not p.exists()
    assert s.stats(1)["attempts"] == 0
    corrupt = list(tmp_path.glob("users.json.corrupt-*"))
    assert len(corrupt) == 1


def test_quarantine_invalid_utf8(tmp_path):
    p = _path(tmp_path)
    p.write_bytes(b"\xff\xfe{}")
    s = Store(p)
    assert not p.exists()
    assert s.stats(1)["attempts"] == 0
    assert len(list(tmp_path.glob("users.json.corrupt-*"))) == 1


def test_quarantine_non_dict_top_level(tmp_path):
    p = _path(tmp_path)
    p.write_text("[1, 2]", encoding="utf-8")
    s = Store(p)
    assert not p.exists()
    assert s.stats(1)["attempts"] == 0
    assert len(list(tmp_path.glob("users.json.corrupt-*"))) == 1


def test_double_quarantine_two_distinct_files(tmp_path):
    p = _path(tmp_path)
    p.write_text("{bad", encoding="utf-8")
    Store(p)  # первый карантин
    p.write_text("{bad", encoding="utf-8")
    Store(p)  # второй карантин в ту же секунду
    files = list(tmp_path.glob("users.json.corrupt-*"))
    assert len(files) == 2
    assert len({f.name for f in files}) == 2  # разные имена


# --- нормализация битых записей ---


def test_entry_normalization_load(tmp_path):
    p = _path(tmp_path)
    data = {
        "10": {
            "attempts": "abc",            # не int → 0
            "total_correct": "5",         # строка-число → 5
            "total_possible": "7",        # строка-число → 7
            "completed": [1, "x", 3],     # "x" отбрасывается → [1, 3]
            "conflictogens": {
                "a": {"present": "3", "correct": "bad", "false_positive": 1},
                "b": {"present": 2, "correct": 5},  # correct > present → clamp
            },
        },
        "99": "not-a-dict",               # не-объект → отбрасывается
    }
    p.write_text(json.dumps(data), encoding="utf-8")
    s = Store(p)
    st = s.stats(10)
    assert st["attempts"] == 0
    assert st["total_correct"] == 5
    assert st["total_possible"] == 7
    assert st["completed"] == [1, 3]
    assert st["conflictogens"] == {
        "a": {"present": 3, "correct": 0, "false_positive": 1},
        "b": {"present": 2, "correct": 2, "false_positive": 0},
    }
    assert "best" not in st
    assert "99" not in s._data  # не-объектная запись отброшена


def test_entry_normalization_completed_ids(tmp_path):
    p = _path(tmp_path)
    p.write_text(json.dumps({"10": {"completed": [1, "x", 3]}}), encoding="utf-8")
    s = Store(p)
    assert s.completed_ids(10) == {1, 3}


def test_entry_normalization_record_attempt(tmp_path):
    p = _path(tmp_path)
    data = {
        "10": {
            "attempts": "abc",
            "total_correct": "5",
            "total_possible": "7",
            "completed": [1, "x", 3],
            "conflictogens": {"a": {"present": 1, "correct": 1, "false_positive": 0}},
        }
    }
    p.write_text(json.dumps(data), encoding="utf-8")
    s = Store(p)
    # record_attempt не падает на нормализованной записи и накатывается на неё
    s.record_attempt(10, 1, ("a",), ("b",), ())
    st = s.stats(10)
    assert st["attempts"] == 1
    assert st["total_correct"] == 6  # 5 + 1
    assert st["total_possible"] == 9  # 7 + (1 + 1)
    assert st["completed"] == [1, 3]
    assert st["conflictogens"]["a"] == {"present": 2, "correct": 2, "false_positive": 0}
    assert st["conflictogens"]["b"] == {"present": 1, "correct": 0, "false_positive": 0}


def test_cg_stats_corrupt_non_dict(tmp_path):
    p = _path(tmp_path)
    p.write_text(json.dumps({"10": {"conflictogens": "bad"}}), encoding="utf-8")
    s = Store(p)
    assert s.stats(10)["conflictogens"] == {}


def test_cg_stats_corrupt_inner_non_dict(tmp_path):
    p = _path(tmp_path)
    p.write_text(json.dumps({"10": {"conflictogens": {"a": "bad"}}}), encoding="utf-8")
    s = Store(p)
    assert s.stats(10)["conflictogens"] == {
        "a": {"present": 0, "correct": 0, "false_positive": 0},
    }


def test_cg_stats_clamps_correct_to_present(tmp_path):
    p = _path(tmp_path)
    p.write_text(
        json.dumps({"10": {"conflictogens": {"a": {"correct": 5, "present": 2}}}}),
        encoding="utf-8",
    )
    s = Store(p)
    assert s.stats(10)["conflictogens"] == {
        "a": {"present": 2, "correct": 2, "false_positive": 0},
    }


def test_cg_stats_clamps_negative_counters_to_zero(tmp_path):
    # Отрицательные счётчики (только через битый файл) → ноль; при этом
    # correct клампится по клампнутому present, так что инвариант
    # 0 <= correct <= present не ломается (раньше получался {"present": -1, "correct": -1}).
    p = _path(tmp_path)
    p.write_text(
        json.dumps(
            {"10": {"conflictogens": {"a": {"present": -1, "correct": 3, "false_positive": -2}}}}
        ),
        encoding="utf-8",
    )
    s = Store(p)
    assert s.stats(10)["conflictogens"] == {
        "a": {"present": 0, "correct": 0, "false_positive": 0},
    }


def test_legacy_entry_best_dropped(tmp_path):
    # Старая запись с «best» и без «conflictogens»: загружается безопасно,
    # «best» исчезает из stats(), «conflictogens» — пустой словарь.
    p = _path(tmp_path)
    p.write_text(json.dumps({"10": {"attempts": 1, "best": {"1": 3}}}), encoding="utf-8")
    s = Store(p)
    st = s.stats(10)
    assert st["attempts"] == 1
    assert "best" not in st
    assert st["conflictogens"] == {}


# --- бесконечности из битого JSON ---


def test_coerce_int_infinity_returns_default():
    # int(float('inf')) бросает OverflowError — ловим и возвращаем default,
    # а не падаем при загрузке (json.loads принимает Infinity по умолчанию).
    assert _coerce_int(float("inf")) == 0
    assert _coerce_int(float("-inf")) == 0
    assert _coerce_int(float("inf"), 5) == 5


def test_load_normalizes_infinity_counters(tmp_path):
    # Реалистичный битый файл: json.dumps по умолчанию пишет Infinity,
    # json.loads читает обратно — загрузка не падает, счётчики → 0.
    p = _path(tmp_path)
    p.write_text(
        json.dumps({"10": {"attempts": float("inf"), "total_correct": float("-inf")}}),
        encoding="utf-8",
    )
    s = Store(p)
    st = s.stats(10)
    assert st["attempts"] == 0
    assert st["total_correct"] == 0


# --- персистентность ---


def test_persistence_round_trip(tmp_path):
    p = _path(tmp_path)
    s = Store(p)
    s.record_attempt(1, 5, ("a",), ("b",), ())
    s.record_attempt(1, 9, ("a", "c"), (), ("b",))

    s2 = Store(p)  # переинициализация на том же пути
    st = s2.stats(1)
    assert st["attempts"] == 2
    assert st["total_correct"] == 3
    assert st["total_possible"] == 4  # (1+1) + (2+0)
    assert st["completed"] == [5, 9]
    assert s2.completed_ids(1) == {5, 9}
    assert st["conflictogens"] == {
        "a": {"present": 2, "correct": 2, "false_positive": 0},
        "b": {"present": 1, "correct": 0, "false_positive": 1},
        "c": {"present": 1, "correct": 1, "false_positive": 0},
    }
