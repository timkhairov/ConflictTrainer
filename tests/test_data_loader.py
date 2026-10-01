"""Тесты загрузки и валидации данных (bot/data_loader.py).

Валидация проверяется на синтетических файлах в tmp_path: записываем корректную
базовую структуру и мутируем конкретное поле. Обязательные текстовые поля
(name/phrase/domain) должны присутствовать как непустые строки; необязательные
(description/note/icon) — опциональные: отсутствующий ключ или JSON null дают "",
присутствующее значение обязано быть строкой (bool/числа отклоняются).
"""
from collections import Counter
import json

import pytest

from bot.config import DATA_DIR
from bot.data_loader import (
    DataError,
    load_all,
    load_conflictogens,
    load_domains,
    load_exercises,
    load_subjects,
)
from bot.models import Subject

# Известные сферы для синтетических упражнений (по умолчанию — "d1")
DOMS = {"d1", "d2"}
# Известные темы для синтетических упражнений
SUBJECTS = {
    "s1": Subject(id="s1", name="S1", domain="d1"),
    "s2": Subject(id="s2", name="S2", domain="d2"),
}


def _write(path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _load_conf(tmp_path, items):
    p = tmp_path / "conflictogens.json"
    _write(p, {"conflictogens": items})
    return load_conflictogens(p)


def _load_doms(tmp_path, items, with_key=True):
    p = tmp_path / "domains.json"
    _write(p, {"domains": items} if with_key else {"other": items})
    return load_domains(p)


def _load_subs(tmp_path, items, known_domains=DOMS, with_key=True):
    p = tmp_path / "subjects.json"
    _write(p, {"subjects": items} if with_key else {"other": items})
    return load_subjects(p, set(known_domains))


def _load_ex(tmp_path, items, known, known_domains=DOMS, known_subjects=SUBJECTS):
    p = tmp_path / "exercises.json"
    _write(p, {"exercises": items})
    return load_exercises(p, set(known), set(known_domains), known_subjects)


# --- реальная библиотека данных ---


def test_load_all_real_data():
    domains, subjects, conflictogens, exercises = load_all(DATA_DIR)
    assert [d.id for d in domains] == ["work", "family"]
    assert [d.name for d in domains] == ["Работа", "Семья"]
    assert len(subjects) == 12
    assert len(conflictogens) == 7
    assert len(exercises) == 188
    assert [e.id for e in exercises] == list(range(1, 189))
    assert all(e.domain == "work" for e in exercises[:88])
    assert all(e.domain == "family" for e in exercises[88:])
    assert exercises[87].conflictogens == ()  # последний рабочий контрольный пример
    ids = {c.id for c in conflictogens}
    subs = {s.id: s for s in subjects}
    for e in exercises:
        for cid in e.conflictogens:
            assert cid in ids, f"unknown conflictogen {cid} in exercise {e.id}"
        assert e.subject in subs, f"unknown subject {e.subject!r} in exercise {e.id}"
        assert subs[e.subject].domain == e.domain, (
            f"exercise {e.id}: subject {e.subject!r} domain "
            f"{subs[e.subject].domain!r} != exercise domain {e.domain!r}"
        )


def test_family_exercises_real_data_quality():
    _, _, conflictogens, exercises = load_all(DATA_DIR)
    family = [exercise for exercise in exercises if exercise.domain == "family"]
    known_ids = {conflictogen.id for conflictogen in conflictogens}

    assert [exercise.id for exercise in family] == list(range(89, 189))
    assert Counter(len(exercise.conflictogens) for exercise in family) == {
        0: 12,
        1: 36,
        2: 52,
    }
    assert max(len(exercise.conflictogens) for exercise in family) == 2
    assert Counter(
        cid for exercise in family for cid in exercise.conflictogens
    ) == {cid: 20 for cid in known_ids}

    phrases = [exercise.phrase.strip() for exercise in family]
    assert all(exercise.phrase == exercise.phrase.strip() for exercise in family)
    assert len(phrases) == len(set(phrases)) == 100
    assert all(exercise.note.strip() for exercise in family)

    for exercise in family:
        mentioned_ids = {cid for cid in known_ids if cid in exercise.note}
        assert mentioned_ids == set(exercise.conflictogens)
        if not exercise.conflictogens:
            assert "Контрольный пример" in exercise.note


# --- domains: реальный файл и базовые проверки ---


def test_load_domains_real_data():
    domains = load_domains(DATA_DIR / "domains.json")
    assert len(domains) == 2
    work, family = domains
    assert (work.id, work.name) == ("work", "Работа")
    assert (family.id, family.name) == ("family", "Семья")
    assert work.icon and family.icon  # у обеих сфер задан эмодзи-префикс


def test_domain_null_icon_defaults_to_empty(tmp_path):
    result = _load_doms(tmp_path, [{"id": "a", "name": "A", "icon": None}])
    assert result[0].icon == ""


def test_domain_missing_icon_defaults_to_empty(tmp_path):
    result = _load_doms(tmp_path, [{"id": "a", "name": "A"}])
    assert result[0].icon == ""


def test_domain_icon_16_accepted(tmp_path):
    result = _load_doms(tmp_path, [{"id": "a", "name": "A", "icon": "i" * 16}])
    assert len(result[0].icon) == 16


def test_domain_icon_17_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_doms(tmp_path, [{"id": "a", "name": "A", "icon": "i" * 17}])


def test_domain_icon_as_bool_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_doms(tmp_path, [{"id": "a", "name": "A", "icon": True}])


def test_domain_icon_plus_name_button_64_accepted(tmp_path):
    # подпись кнопки «icon name»: 16 + 1 + 47 = 64 символа → в пределах лимита
    result = _load_doms(tmp_path, [{"id": "a", "name": "n" * 47, "icon": "i" * 16}])
    assert len(f"{result[0].icon} {result[0].name}") == 64


def test_domain_icon_plus_name_button_65_rejected(tmp_path):
    # 16 + 1 + 48 = 65 символов в подписи кнопки → BUTTON_TEXT_INVALID в Telegram,
    # хотя каждое поле по отдельности проходит свои лимиты
    with pytest.raises(DataError, match=r"подпись кнопки"):
        _load_doms(tmp_path, [{"id": "a", "name": "n" * 48, "icon": "i" * 16}])


# --- domains: отклонения ---


def test_domain_missing_list_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_doms(tmp_path, [{"id": "a", "name": "A"}], with_key=False)


def test_domain_empty_list_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_doms(tmp_path, [])


def test_domain_missing_name_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_doms(tmp_path, [{"id": "a"}])


def test_domain_name_as_bool_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_doms(tmp_path, [{"id": "a", "name": True}])


def test_domain_id_bool_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_doms(tmp_path, [{"id": True, "name": "A"}])


def test_domain_duplicate_id_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_doms(tmp_path, [
            {"id": "a", "name": "A"},
            {"id": "a", "name": "B"},
        ])


# --- domains: границы длины ---


def test_domain_id_payload_64_bytes_accepted(tmp_path):
    # "dom:" (4 байта) + 60 = 64 байта → в пределах лимита
    did = "a" * 60
    assert len(("dom:" + did).encode("utf-8")) == 64
    result = _load_doms(tmp_path, [{"id": did, "name": "A"}])
    assert result[0].id == did


def test_domain_id_payload_65_bytes_rejected(tmp_path):
    # 4 + 61 = 65 байт → превышает лимит Telegram
    did = "a" * 61
    assert len(("dom:" + did).encode("utf-8")) == 65
    with pytest.raises(DataError):
        _load_doms(tmp_path, [{"id": did, "name": "A"}])


def test_domain_name_62_accepted(tmp_path):
    result = _load_doms(tmp_path, [{"id": "a", "name": "x" * 62}])
    assert len(result[0].name) == 62


def test_domain_name_63_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_doms(tmp_path, [{"id": "a", "name": "x" * 63}])


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
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "s1", "note": ""},
            {"id": 1, "phrase": "y", "conflictogens": ["b"], "domain": "d1", "subject": "s1", "note": ""},
        ], {"a", "b"})


def test_exercise_unknown_conflictogen_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["zzz"], "domain": "d1", "subject": "s1", "note": ""},
        ], {"a", "b"})


def test_exercise_empty_list_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [], {"a", "b"})


def test_exercise_empty_conflictogens_accepted(tmp_path):
    # пустой список conflictogens — контрольный пример (фразы без конфликтогенов)
    result = _load_ex(
        tmp_path, [{"id": 1, "phrase": "x", "conflictogens": [], "domain": "d1", "subject": "s1"}], {"a", "b"}
    )
    assert len(result) == 1
    assert result[0].conflictogens == ()


def test_exercise_missing_conflictogens_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [{"id": 1, "phrase": "x", "domain": "d1", "subject": "s1"}], {"a", "b"})


def test_exercise_conflictogens_non_list_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(
            tmp_path,
            [{"id": 1, "phrase": "x", "conflictogens": "a", "domain": "d1", "subject": "s1"}],
            {"a", "b"},
        )


def test_exercise_id_float_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"id": 1.5, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "s1", "note": ""},
        ], {"a", "b"})


def test_exercise_id_bool_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"id": True, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "s1", "note": ""},
        ], {"a", "b"})


def test_exercise_id_string_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"id": "1", "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "s1", "note": ""},
        ], {"a", "b"})


def test_exercise_id_missing_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "s1", "note": ""},
        ], {"a", "b"})


def test_exercise_missing_phrase_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"id": 1, "conflictogens": ["a"], "domain": "d1", "note": ""},
        ], {"a", "b"})


def test_exercise_phrase_as_bool_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": True, "conflictogens": ["a"], "domain": "d1", "subject": "s1", "note": ""},
        ], {"a", "b"})


def test_exercise_note_as_bool_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "s1", "note": True},
        ], {"a", "b"})


def test_exercise_missing_note_defaults_to_empty(tmp_path):
    # note — необязательное поле (README: «необязательное пояснение к разбору»,
    # дефолт Exercise.note = ""): отсутствие ключа не должно ломать загрузку.
    result = _load_ex(
        tmp_path, [{"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "s1"}], {"a", "b"}
    )
    assert len(result) == 1
    assert result[0].note == ""


def test_exercise_null_note_defaults_to_empty(tmp_path):
    # JSON null эквивалентен отсутствию ключа → ""
    result = _load_ex(
        tmp_path,
        [{"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "s1", "note": None}],
        {"a", "b"},
    )
    assert result[0].note == ""


# --- exercises: поле domain ---


def test_exercise_domain_loaded(tmp_path):
    result = _load_ex(tmp_path, [
        {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d2", "subject": "s2"},
    ], {"a"})
    assert result[0].domain == "d2"


def test_exercise_missing_domain_rejected(tmp_path):
    with pytest.raises(DataError, match=r"exercises\[0\] \(id=1\).*domain"):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "note": ""},
        ], {"a", "b"})


def test_exercise_empty_domain_rejected(tmp_path):
    with pytest.raises(DataError, match=r"exercises\[0\] \(id=1\).*domain"):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "  ", "note": ""},
        ], {"a", "b"})


def test_exercise_domain_as_bool_rejected(tmp_path):
    with pytest.raises(DataError, match=r"exercises\[0\] \(id=1\).*domain"):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": True, "note": ""},
        ], {"a", "b"})


def test_exercise_unknown_domain_rejected_names_record_and_available_ids(tmp_path):
    # ошибка называет конкретную запись и перечисляет доступные id сфер
    with pytest.raises(DataError, match=r"exercises\[2\] \(id=3\): неизвестная сфера 'ghost'") as ei:
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "s1"},
            {"id": 2, "phrase": "y", "conflictogens": ["a"], "domain": "d1", "subject": "s1"},
            {"id": 3, "phrase": "z", "conflictogens": ["a"], "domain": "ghost"},
        ], {"a"})
    assert "Доступные id: ['d1', 'd2']" in str(ei.value)


# --- exercises: поле subject ---


def test_exercise_subject_loaded(tmp_path):
    result = _load_ex(tmp_path, [
        {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "s1"},
    ], {"a"})
    assert result[0].subject == "s1"


def test_exercise_missing_subject_rejected(tmp_path):
    with pytest.raises(DataError, match=r"exercises\[0\] \(id=1\).*subject"):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "note": ""},
        ], {"a", "b"})


def test_exercise_empty_subject_rejected(tmp_path):
    with pytest.raises(DataError, match=r"exercises\[0\] \(id=1\).*subject"):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "  "},
        ], {"a", "b"})


def test_exercise_subject_as_bool_rejected(tmp_path):
    with pytest.raises(DataError, match=r"exercises\[0\] \(id=1\).*subject"):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": True},
        ], {"a", "b"})


def test_exercise_unknown_subject_rejected(tmp_path):
    with pytest.raises(DataError, match=r"exercises\[0\] \(id=1\): неизвестная тема 'ghost'"):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "ghost"},
        ], {"a"})
    # доступные id перечислены


def test_exercise_subject_wrong_domain_rejected(tmp_path):
    # s2 относится к d2, а упражнение в d1 → несовпадение
    with pytest.raises(DataError, match=r"exercises\[0\] \(id=1\).*относится к сфере"):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "s2"},
        ], {"a"})


# --- subjects: отклонения ---


def test_subject_loaded(tmp_path):
    result = _load_subs(tmp_path, [{"id": "a", "name": "A", "domain": "d1"}])
    assert len(result) == 1
    assert (result[0].id, result[0].name, result[0].domain) == ("a", "A", "d1")


def test_subject_missing_list_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_subs(tmp_path, [{"id": "a", "name": "A", "domain": "d1"}], with_key=False)


def test_subject_empty_list_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_subs(tmp_path, [])


def test_subject_missing_name_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_subs(tmp_path, [{"id": "a", "domain": "d1"}])


def test_subject_name_as_bool_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_subs(tmp_path, [{"id": "a", "name": True, "domain": "d1"}])


def test_subject_missing_domain_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_subs(tmp_path, [{"id": "a", "name": "A"}])


def test_subject_unknown_domain_rejected(tmp_path):
    with pytest.raises(DataError, match=r"неизвестная сфера"):
        _load_subs(tmp_path, [{"id": "a", "name": "A", "domain": "ghost"}])


def test_subject_duplicate_id_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_subs(tmp_path, [
            {"id": "a", "name": "A", "domain": "d1"},
            {"id": "a", "name": "B", "domain": "d1"},
        ])


def test_subject_id_payload_64_bytes_accepted(tmp_path):
    sid = "a" * 60
    assert len(("sub:" + sid).encode("utf-8")) == 64
    result = _load_subs(tmp_path, [{"id": sid, "name": "A", "domain": "d1"}])
    assert result[0].id == sid


def test_subject_id_payload_65_bytes_rejected(tmp_path):
    sid = "a" * 61
    assert len(("sub:" + sid).encode("utf-8")) == 65
    with pytest.raises(DataError):
        _load_subs(tmp_path, [{"id": sid, "name": "A", "domain": "d1"}])


def test_subject_name_62_accepted(tmp_path):
    result = _load_subs(tmp_path, [{"id": "a", "name": "x" * 62, "domain": "d1"}])
    assert len(result[0].name) == 62


def test_subject_name_63_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_subs(tmp_path, [{"id": "a", "name": "x" * 63, "domain": "d1"}])


# --- exercises: границы длины ---


def test_exercise_phrase_1500_accepted(tmp_path):
    result = _load_ex(tmp_path, [
        {"id": 1, "phrase": "p" * 1500, "conflictogens": ["a"], "domain": "d1", "subject": "s1", "note": ""},
    ], {"a", "b"})
    assert len(result[0].phrase) == 1500


def test_exercise_phrase_1501_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "p" * 1501, "conflictogens": ["a"], "domain": "d1", "subject": "s1", "note": ""},
        ], {"a", "b"})


def test_exercise_note_1000_accepted(tmp_path):
    result = _load_ex(tmp_path, [
        {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "s1", "note": "n" * 1000},
    ], {"a", "b"})
    assert len(result[0].note) == 1000


def test_exercise_note_1001_rejected(tmp_path):
    with pytest.raises(DataError):
        _load_ex(tmp_path, [
            {"id": 1, "phrase": "x", "conflictogens": ["a"], "domain": "d1", "subject": "s1", "note": "n" * 1001},
        ], {"a", "b"})
