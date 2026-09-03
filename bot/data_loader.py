"""Загрузка и валидация данных из JSON-файлов.

Все ошибки приведены к :class:`DataError` с человекочитаемым сообщением,
чтобы при неверных данных бот не падал с непонятным traceback, а сообщал
конкретно, что именно не так и в какой записи.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .keyboards import CB_TOGGLE
from .models import Conflictogen, Exercise


class DataError(Exception):
    """Ошибка структуры или содержания данных."""


# --- лимиты Telegram (см. README и keyboards.py) ---
CALLBACK_DATA_MAX_BYTES = 64  # callback_data: 1–64 байта
# Имя конфликтогена: лимит подписи кнопки Telegram 64 символа минус знак выбора
# «✓ »/«• » (2 символа, см. keyboards.exercise_keyboard) = 62, иначе BUTTON_TEXT_INVALID.
NAME_MAX_LEN = 62             # имя конфликтогена на кнопке
DESCRIPTION_MAX_LEN = 500     # описание конфликтогена
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


def load_exercises(path: Path, known_ids: set[str]) -> list[Exercise]:
    """Загружает и проверяет упражнения (id конфликтогенов должны существовать)."""
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

        note = _optional_str(item.get("note"), ctx, "note")
        _check_len(note, NOTE_MAX_LEN, ctx, "note")
        result.append(
            Exercise(
                id=eid,
                phrase=phrase,
                conflictogens=tuple(cogs),
                note=note,
            )
        )
    if not result:
        raise DataError(f"{path}: список упражнений пуст")
    return result


def load_all(data_dir: Path) -> tuple[list[Conflictogen], list[Exercise]]:
    """Загружает оба файла и возвращает (конфликтогены, упражнения)."""
    conflictogens = load_conflictogens(data_dir / "conflictogens.json")
    known = {c.id for c in conflictogens}
    exercises = load_exercises(data_dir / "exercises.json", known)
    return conflictogens, exercises
