"""Загрузка и валидация данных из JSON-файлов.

Все ошибки приведены к :class:`DataError` с человекочитаемым сообщением,
чтобы при неверных данных бот не падал с непонятным traceback, а сообщал
конкретно, что именно не так и в какой записи.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .keyboards import CB_DOMAIN, CB_SUBJECT, CB_TOGGLE
from .models import Conflictogen, Domain, Exercise, Subject


class DataError(Exception):
    """Ошибка структуры или содержания данных."""


# --- лимиты Telegram (см. README и keyboards.py) ---
CALLBACK_DATA_MAX_BYTES = 64  # callback_data: 1–64 байт
# Лимит подписи кнопки Telegram — 64 символа.
BUTTON_TEXT_MAX_LEN = 64
# Имя конфликтогена: 64 минус знак выбора «✓ »/«• » (2 символа,
# см. keyboards.exercise_keyboard) = 62, иначе BUTTON_TEXT_INVALID.
NAME_MAX_LEN = 62             # имя конфликтогена на кнопке (и название сферы)
DESCRIPTION_MAX_LEN = 500     # описание конфликтогена
ICON_MAX_LEN = 16             # эмодзи-префикс сферы жизни на кнопке
PHRASE_MAX_LEN = 1500         # фраза упражнения
NOTE_MAX_LEN = 1000           # пояснение к разбору


def _check_len(value: str, limit: int, ctx: str, field: str) -> None:
    """Бросает DataError, если поле длиннее лимита."""
    if len(value) > limit:
        raise DataError(
            f"{ctx}: поле \"{field}\" длиннее {limit} символов (сейчас {len(value)})"
        )


def _require_str(value: Any, ctx: str, field: str, *, allow_empty: bool) -> str:
    """Текстовое поле данных: обязательно строка (bool/числа/None отклоняются).

    Возвращает строку без пробелов по краям. Если allow_empty=False и строка
    пустая — DataError. Аналог проверки id: тип проверяется явно, а не через str().
    """
    if not isinstance(value, str):
        raise DataError(
            f"{ctx}: поле \"{field}\" должно быть строкой (получено {type(value).__name__})"
        )
    text = value.strip()
    if not allow_empty and not text:
        raise DataError(f"{ctx}: не задано поле \"{field}\"")
    return text


def _optional_str(value: Any, ctx: str, field: str) -> str:
    """Необязательное текстовое поле: отсутствующий ключ (None, в т.ч. JSON null)
    → пустая строка "", а присутствующее значение обязано быть строкой
    (bool/числа/другие типы отклоняются). Аналог :func:`_require_str` с allow_empty=True.
    """
    if value is None:
        return ""
    return _require_str(value, ctx, field, allow_empty=True)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise DataError(f"Файл не найден: {path}") from e
    except json.JSONDecodeError as e:
        raise DataError(f"Некорректный JSON в {path}: {e}") from e
    if not isinstance(data, dict):
        raise DataError(f"{path}: ожидается объект JSON ({{...}}) на верхнем уровне")
    return data


def load_conflictogens(path: Path) -> list[Conflictogen]:
    """Загружает и проверяет список конфликтогенов."""
    raw = _read_json(path)
    items = raw.get("conflictogens")
    if not isinstance(items, list):
        raise DataError(f"{path}: отсутствует список \"conflictogens\"")

    result: list[Conflictogen] = []
    seen: set[str] = set()
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise DataError(f"conflictogens[{i - 1}]: запись должна быть объектом")
        ctx = f"conflictogens[{i - 1}]"
        raw_id = item.get("id")
        if not isinstance(raw_id, str):
            raise DataError(
                f"{ctx}: id должен быть строкой (получено {type(raw_id).__name__}); "
                f"используйте короткий латинский ключ, например \"generalization\""
            )
        cid = raw_id.strip()
        if not cid:
            raise DataError(f"{ctx}: не задан id")
        payload = f"{CB_TOGGLE}{cid}"
        if len(payload.encode("utf-8")) > CALLBACK_DATA_MAX_BYTES:
            raise DataError(
                f"{ctx} (id={cid!r}): callback-данные {payload!r} длиннее "
                f"{CALLBACK_DATA_MAX_BYTES} байт (лимит Telegram) — сделайте id короче"
            )
        ctx_id = f"{ctx} (id={cid!r})"
        name = _require_str(item.get("name"), ctx_id, "name", allow_empty=False)
        if cid in seen:
            raise DataError(f"conflictogens: дублирующийся id {cid!r}")
        seen.add(cid)
        description = _optional_str(item.get("description"), ctx_id, "description")
        _check_len(name, NAME_MAX_LEN, ctx_id, "name")
        _check_len(description, DESCRIPTION_MAX_LEN, ctx_id, "description")
        result.append(
            Conflictogen(
                id=cid,
                name=name,
                description=description,
            )
        )
    if not result:
        raise DataError(f"{path}: список конфликтогенов пуст")
    return result


def load_domains(path: Path) -> list[Domain]:
    """Загружает и проверяет список сфер жизни."""
    raw = _read_json(path)
    items = raw.get("domains")
    if not isinstance(items, list):
        raise DataError(f"{path}: отсутствует список \"domains\"")

    result: list[Domain] = []
    seen: set[str] = set()
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise DataError(f"domains[{i - 1}]: запись должна быть объектом")
        ctx = f"domains[{i - 1}]"
        raw_id = item.get("id")
        if not isinstance(raw_id, str):
            raise DataError(
                f"{ctx}: id должен быть строкой (получено {type(raw_id).__name__}); "
                f"используйте короткий латинский ключ, например \"work\""
            )
        did = raw_id.strip()
        if not did:
            raise DataError(f"{ctx}: не задан id")
        payload = f"{CB_DOMAIN}{did}"
        if len(payload.encode("utf-8")) > CALLBACK_DATA_MAX_BYTES:
            raise DataError(
                f"{ctx} (id={did!r}): callback-данные {payload!r} длиннее "
                f"{CALLBACK_DATA_MAX_BYTES} байт (лимит Telegram) — сделайте id короче"
            )
        ctx_id = f"{ctx} (id={did!r})"
        name = _require_str(item.get("name"), ctx_id, "name", allow_empty=False)
        if did in seen:
            raise DataError(f"domains: дублирующийся id {did!r}")
        seen.add(did)
        icon = _optional_str(item.get("icon"), ctx_id, "icon")
        _check_len(name, NAME_MAX_LEN, ctx_id, "name")
        _check_len(icon, ICON_MAX_LEN, ctx_id, "icon")
        # Кнопка сферы собирается из icon + пробел + name (keyboards.domain_keyboard),
        # поэтому проверяем длину композиции, а не только полей по отдельности.
        button_text = f"{icon} {name}".strip()
        if len(button_text) > BUTTON_TEXT_MAX_LEN:
            raise DataError(
                f"{ctx_id}: подпись кнопки \"{button_text}\" длиннее "
                f"{BUTTON_TEXT_MAX_LEN} символов (сейчас {len(button_text)}) — "
                f"сократите icon или name"
            )
        result.append(
            Domain(
                id=did,
                name=name,
                icon=icon,
            )
        )
    if not result:
        raise DataError(f"{path}: список сфер пуст")
    return result


def load_subjects(path: Path, known_domains: set[str]) -> list[Subject]:
    """Загружает и проверяет список тем (субъектов) внутри сфер."""
    raw = _read_json(path)
    items = raw.get("subjects")
    if not isinstance(items, list):
        raise DataError(f"{path}: отсутствует список \"subjects\"")

    result: list[Subject] = []
    seen: set[str] = set()
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise DataError(f"subjects[{i - 1}]: запись должна быть объектом")
        ctx = f"subjects[{i - 1}]"
        raw_id = item.get("id")
        if not isinstance(raw_id, str):
            raise DataError(
                f"{ctx}: id должен быть строкой (получено {type(raw_id).__name__}); "
                f"используйте короткий латинский ключ, например \"salary\""
            )
        sid = raw_id.strip()
        if not sid:
            raise DataError(f"{ctx}: не задан id")
        payload = f"{CB_SUBJECT}{sid}"
        if len(payload.encode("utf-8")) > CALLBACK_DATA_MAX_BYTES:
            raise DataError(
                f"{ctx} (id={sid!r}): callback-данные {payload!r} длиннее "
                f"{CALLBACK_DATA_MAX_BYTES} байт (лимит Telegram) — сделайте id короче"
            )
        ctx_id = f"{ctx} (id={sid!r})"
        name = _require_str(item.get("name"), ctx_id, "name", allow_empty=False)
        if sid in seen:
            raise DataError(f"subjects: дублирующийся id {sid!r}")
        seen.add(sid)
        domain = _require_str(item.get("domain"), ctx_id, "domain", allow_empty=False)
        if domain not in known_domains:
            raise DataError(
                f"{ctx_id}: неизвестная сфера {domain!r}. "
                f"Доступные id: {sorted(known_domains)}"
            )
        _check_len(name, NAME_MAX_LEN, ctx_id, "name")
        result.append(
            Subject(
                id=sid,
                name=name,
                domain=domain,
            )
        )
    if not result:
        raise DataError(f"{path}: список тем пуст")
    return result


def load_exercises(
    path: Path,
    known_ids: set[str],
    known_domains: set[str],
    known_subjects: dict[str, Subject],
) -> list[Exercise]:
    """Загружает и проверяет упражнения.

    id конфликтогенов, сфер и тем должны существовать; тема должна
    относиться к той же сфере, что и упражнение.
    """
    raw = _read_json(path)
    items = raw.get("exercises")
    if not isinstance(items, list):
        raise DataError(f"{path}: отсутствует список \"exercises\"")

    result: list[Exercise] = []
    seen_ids: set[int] = set()
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise DataError(f"exercises[{i - 1}]: запись должна быть объектом")

        eid_raw = item.get("id")
        if eid_raw is None:
            raise DataError(f"exercises[{i - 1}]: не задан id")
        if not (isinstance(eid_raw, int) and not isinstance(eid_raw, bool)):
            raise DataError(f"exercises[{i - 1}]: id должен быть целым числом")
        eid = eid_raw
        if eid in seen_ids:
            raise DataError(f"exercises: дублирующийся id {eid}")
        seen_ids.add(eid)

        ctx = f"exercises[{i - 1}] (id={eid})"
        phrase = _require_str(item.get("phrase"), ctx, "phrase", allow_empty=False)
        _check_len(phrase, PHRASE_MAX_LEN, ctx, "phrase")

        cogs_raw = item.get("conflictogens")
        if not isinstance(cogs_raw, list):
            raise DataError(
                f"exercises[{i - 1}] (id={eid}): поле \"conflictogens\" должно быть списком "
                f"(пустой список допустим — контрольный пример без конфликтогенов)"
            )
        # Убираем дубликаты, сохраняя порядок. Пустой список — валидный
        # контрольный пример: фраза без зашитых конфликтогенов.
        cogs = list(dict.fromkeys(str(c).strip() for c in cogs_raw))
        unknown = [c for c in cogs if c not in known_ids]
        if unknown:
            raise DataError(
                f"exercises[{i - 1}] (id={eid}): неизвестные конфликтогены {unknown}. "
                f"Доступные id: {sorted(known_ids)}"
            )

        domain = _require_str(item.get("domain"), ctx, "domain", allow_empty=False)
        if domain not in known_domains:
            raise DataError(
                f"exercises[{i - 1}] (id={eid}): неизвестная сфера {domain!r}. "
                f"Доступные id: {sorted(known_domains)}"
            )

        subject = _require_str(item.get("subject"), ctx, "subject", allow_empty=False)
        subj = known_subjects.get(subject)
        if subj is None:
            raise DataError(
                f"{ctx}: неизвестная тема {subject!r}. "
                f"Доступные id: {sorted(known_subjects)}"
            )
        if subj.domain != domain:
            raise DataError(
                f"{ctx}: тема {subject!r} относится к сфере {subj.domain!r}, "
                f"а упражнение указано в сфере {domain!r}"
            )

        note = _optional_str(item.get("note"), ctx, "note")
        _check_len(note, NOTE_MAX_LEN, ctx, "note")
        result.append(
            Exercise(
                id=eid,
                phrase=phrase,
                conflictogens=tuple(cogs),
                domain=domain,
                subject=subject,
                note=note,
            )
        )
    if not result:
        raise DataError(f"{path}: список упражнений пуст")
    return result


def load_all(
    data_dir: Path,
) -> tuple[list[Domain], list[Subject], list[Conflictogen], list[Exercise]]:
    """Загружает все файлы и возвращает (сферы, темы, конфликтогены, упражнения)."""
    domains = load_domains(data_dir / "domains.json")
    known_doms = {d.id for d in domains}
    subjects = load_subjects(data_dir / "subjects.json", known_doms)
    known_subjects = {s.id: s for s in subjects}
    conflictogens = load_conflictogens(data_dir / "conflictogens.json")
    known = {c.id for c in conflictogens}
    exercises = load_exercises(
        data_dir / "exercises.json", known, known_doms, known_subjects
    )
    return domains, subjects, conflictogens, exercises
