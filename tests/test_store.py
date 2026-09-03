"""Тесты хранилища прогресса (bot/store.py).

Покрыты: поведение при отсутствии файла, накопление статистики, quarantine
повреждённых файлов (невалидный JSON / не-UTF-8 / не-объект) и нормализация
битых записей, а также персистентность.
"""
import json

from bot.store import Store


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
    assert st["best"] == {}
    assert s.completed_ids(1) == set()


def test_missing_file_first_record_creates_file(tmp_path):
    p = _path(tmp_path)
    assert not p.exists()
    s = Store(p)
    s.record_attempt(1, 1, 1, 1)
    assert p.exists()


# --- накопление статистики ---


def test_record_attempt_increments_and_accumulates(tmp_path):
    s = Store(_path(tmp_path))
    s.record_attempt(1, 1, 3, 4)
    s.record_attempt(1, 1, 1, 4)  # более низкий счёт, то же упражнение
    st = s.stats(1)
    assert st["attempts"] == 2
    assert st["total_correct"] == 4  # 3 + 1
    assert st["total_possible"] == 8  # 4 + 4
    assert st["completed"] == [1]  # дедупликация
    assert st["best"] == {"1": 3}  # best хранит максимум


def test_completed_dedupes(tmp_path):
    s = Store(_path(tmp_path))
    s.record_attempt(1, 7, 1, 1)
    s.record_attempt(1, 7, 1, 1)
    s.record_attempt(1, 8, 1, 1)
    assert s.completed_ids(1) == {7, 8}


def test_best_keeps_max(tmp_path):
    s = Store(_path(tmp_path))
    s.record_attempt(1, 1, 5, 10)
    s.record_attempt(1, 1, 2, 10)  # ниже — не затирает
    s.record_attempt(1, 1, 9, 10)  # выше — обновляет
    assert s.stats(1)["best"] == {"1": 9}


def test_stats_accuracy_none_when_no_possible(tmp_path):
    s = Store(_path(tmp_path))
    assert s.stats(1)["accuracy"] is None


def test_stats_accuracy_ratio(tmp_path):
    s = Store(_path(tmp_path))
    s.record_attempt(1, 1, 3, 6)
    assert s.stats(1)["accuracy"] == 3 / 6


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
            "best": {"1": "bad", "2": 2}, # "bad" → 0, 2 → 2
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
    assert st["best"] == {"1": 0, "2": 2}
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
            "best": {"1": "bad", "2": 2},
        }
    }
    p.write_text(json.dumps(data), encoding="utf-8")
    s = Store(p)
    # record_attempt не падает на нормализованной записи
    s.record_attempt(10, 1, 3, 4)
    st = s.stats(10)
    assert st["attempts"] == 1
    assert st["total_correct"] == 8  # 5 + 3
    assert st["total_possible"] == 11  # 7 + 4
    assert st["completed"] == [1, 3]
    assert st["best"] == {"1": 3, "2": 2}  # max(0,3)=3; 3 не > 2


# --- персистентность ---


def test_persistence_round_trip(tmp_path):
    p = _path(tmp_path)
    s = Store(p)
    s.record_attempt(1, 5, 3, 4)
    s.record_attempt(1, 9, 1, 2)

    s2 = Store(p)  # переинициализация на том же пути
    st = s2.stats(1)
    assert st["attempts"] == 2
    assert st["total_correct"] == 4
    assert st["total_possible"] == 6
    assert st["completed"] == [5, 9]
    assert s2.completed_ids(1) == {5, 9}
