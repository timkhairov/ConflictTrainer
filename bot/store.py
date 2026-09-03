"""Хранение прогресса пользователей в JSON-файле.

Лёгкое хранилище «под задачу»: один файл, запись по ключу user_id, потокобезопасная
запись через lock и атомарную замену файла. Для многопользовательского сервера
легко заменить на SQLite/Postgres — интерфейс (stats/record_attempt/completed_ids)
остаётся прежним.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DEFAULTS: dict[str, Any] = {
    "attempts": 0,
    "total_correct": 0,
    "total_possible": 0,
    "completed": [],  # list[int] — id упражнений, которые пользователь уже проходил
    "best": {},       # dict[str, int] — exercise_id(str) -> лучший score_num
}


# --- нормализация записи пользователя (защита от повреждённого JSON) ---

def _coerce_int(value: Any, default: int = 0) -> int:
    """Целое число; bool и нечисловые значения → default (вместо падения)."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_id_list(value: Any) -> list[int]:
    """Список целых id; нецелые/некорректные элементы просто выбрасываются."""
    if not isinstance(value, (list, tuple)):
        return []
    ids: list[int] = []
    for x in value:
        if isinstance(x, bool):
            continue
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    return ids


def _coerce_best(value: Any) -> dict[str, int]:
    """Словарь str → int; некорректные значения сводятся к 0, ключи — к str."""
    if not isinstance(value, dict):
        return {}
    return {str(k): _coerce_int(v, 0) for k, v in value.items()}


def _normalize_entry(entry: Any) -> dict[str, Any] | None:
    """Возвращает «чистую» запись пользователя или None, если entry не объект.

    Поля с неверным типом приводятся к безопасным значениям, чтобы битые записи
    не ломали работу в середине диалога (record_attempt / stats / completed_ids).
    """
    if not isinstance(entry, dict):
        return None
    return {
        "attempts": _coerce_int(entry.get("attempts"), 0),
        "total_correct": _coerce_int(entry.get("total_correct"), 0),
        "total_possible": _coerce_int(entry.get("total_possible"), 0),
        "completed": _coerce_id_list(entry.get("completed")),
        "best": _coerce_best(entry.get("best")),
    }


class Store:
    """Прогресс пользователя: количество попыток, счёт, пройденные упражнения."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = self._load()

    # --- внутреннее чтение/запись ---

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            log.error("Не удалось прочитать %s: %s. Сохраняем файл, начинаем с чистого состояния.",
                      self.path, e)
            self._quarantine()
            return {}
        if not isinstance(loaded, dict):
            log.error("%s: ожидается объект JSON (словарь), а не %s. "
                      "Сохраняем файл, начинаем с чистого состояния.",
                      self.path, type(loaded).__name__)
            self._quarantine()
            return {}
        # Нормализуем каждую запись: битые/не того типа поля приводим к
        # безопасным значениям, записи не-объекты пропускаем (логируем).
        clean: dict[str, dict[str, Any]] = {}
        for user_id, entry in loaded.items():
            normalized = _normalize_entry(entry)
            if normalized is None:
                log.warning("%s: запись пользователя %r не является объектом — пропускаем.",
                            self.path, user_id)
                continue
            clean[str(user_id)] = normalized
        return clean

    def _quarantine(self) -> None:
        """Переименовывает повреждённый файл, чтобы его можно было посмотреть/восстановить.

        В имя включены микросекунды и PID процесса, а при крайне редком
        совпадении добавляется суффикс — иначе повторная карантинизация в ту же
        секунду упёрлась бы в [WinError 183] (переименование на существующее имя).
        """
        stamp = f"{datetime.now():%Y%m%d-%H%M%S-%f}-{os.getpid()}"
        target = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        n = 1
        while target.exists():
            target = self.path.with_name(f"{self.path.name}.corrupt-{stamp}-{n}")
            n += 1
        try:
            self.path.rename(target)
            log.warning("Повреждённый файл сохранён как %s", target)
        except OSError as e:
            log.error("Не удалось переименовать %s: %s. Продолжаем с чистого состояния.",
                      self.path, e)

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)  # атомарная замена

    def _entry(self, user_id: int) -> dict[str, Any]:
        key = str(user_id)
        entry = self._data.get(key)
        if entry is None:
            entry = json.loads(json.dumps(_DEFAULTS))  # глубокая копия дефолтов
            self._data[key] = entry
        return entry

    # --- публичный интерфейс ---

    def record_attempt(
        self, user_id: int, exercise_id: int, score_num: int, score_den: int
    ) -> None:
        """Фиксирует одну попытку и обновляет статистику."""
        with self._lock:
            entry = self._entry(user_id)
            entry["attempts"] = int(entry.get("attempts", 0)) + 1
            entry["total_correct"] = int(entry.get("total_correct", 0)) + score_num
            entry["total_possible"] = int(entry.get("total_possible", 0)) + score_den
            completed: list[int] = entry.setdefault("completed", [])
            if exercise_id not in completed:
                completed.append(exercise_id)
            best: dict[str, int] = entry.setdefault("best", {})
            key = str(exercise_id)
            if score_num > int(best.get(key, 0)):
                best[key] = score_num
            self._persist()

    def stats(self, user_id: int) -> dict[str, Any]:
        """Сводная статистика пользователя (безопасный доступ)."""
        with self._lock:
            entry = self._data.get(str(user_id))
            if entry is None:
                return json.loads(json.dumps(_DEFAULTS)) | {"accuracy": None}
            attempts = int(entry.get("attempts", 0))
            total_possible = int(entry.get("total_possible", 0))
            total_correct = int(entry.get("total_correct", 0))
            accuracy = (total_correct / total_possible) if total_possible else None
            return {
                "attempts": attempts,
                "total_correct": total_correct,
                "total_possible": total_possible,
                "accuracy": accuracy,
                "completed": list(entry.get("completed", [])),
                "best": dict(entry.get("best", {})),
            }

    def completed_ids(self, user_id: int) -> set[int]:
        """Множество id упражнений, которые пользователь уже проходил хотя бы раз."""
        with self._lock:
            entry = self._data.get(str(user_id))
            if entry is None:
                return set()
            return {int(x) for x in entry.get("completed", [])}
