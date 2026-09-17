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
from typing import Any, Sequence

log = logging.getLogger(__name__)

_DEFAULTS: dict[str, Any] = {
    "attempts": 0,
    "total_correct": 0,
    "total_possible": 0,
    "completed": [],    # list[int] — id упражнений, которые пользователь уже проходил
    "conflictogens": {},  # dict[str, dict[str, int]] — id конфликтогена ->
    # {present, correct, false_positive}: сколько раз появлялся / верно
    # найден / помечен лишним
}


# --- нормализация записи пользователя (защита от повреждённого JSON) ---

def _coerce_int(value: Any, default: int = 0) -> int:
    """Целое число; bool, нечисловые значения и бесконечность → default (вместо падения)."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
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


def _coerce_cg_stats(value: Any) -> dict[str, dict[str, int]]:
    """Словарь str → {present, correct, false_positive}, все счётчики — int.

    Не-dict значение → {} (всё выбрасывается). Внутреннее значение не-dict —
    нулевые счётчики (ключ конфликта сохраняется). Каждый счётчик приводится
    через _coerce_int к целому (мусор → 0) и ограничивается снизу нулём,
    ключи — к str. Затем ограничиваем correct сверху present (сначала
    клампим present, потом correct против клампнутого present), чтобы
    инвариант 0 <= correct <= present держался даже на повреждённых файлах.
    """
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, int]] = {}
    for k, v in value.items():
        if not isinstance(v, dict):
            result[str(k)] = {"present": 0, "correct": 0, "false_positive": 0}
            continue
        present = max(0, _coerce_int(v.get("present"), 0))
        correct = max(0, min(_coerce_int(v.get("correct"), 0), present))
        false_positive = max(0, _coerce_int(v.get("false_positive"), 0))
        result[str(k)] = {
            "present": present,
            "correct": correct,
            "false_positive": false_positive,
        }
    return result


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
        "conflictogens": _coerce_cg_stats(entry.get("conflictogens")),
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
        self,
        user_id: int,
        exercise_id: int,
        correct: Sequence[str],
        missed: Sequence[str],
        false_positive: Sequence[str],
    ) -> None:
        """Фиксирует одну попытку и обновляет статистику (общую и по конфликтогенам).

        `correct`/`missed`/`false_positive` — простые строковые id конфликтогенов
        (хранилище не знает про модели домена). Предпосылка: внутри каждого
        аргумента id уникальны (гарантирует evaluate() в bot/scoring.py), поэтому
        каждый id просто добавляет 1 к нужному счётчику.

        Счётчики по конфликтогенам:
        - present — для каждого id из correct И из missed (конфликтоген реально
          был в попытке);
        - correct — для каждого id из correct;
        - false_positive — для каждого id из false_positive (включая «ложные
          тревоги» на контрольных примерах, где correct и missed пусты).
        """
        # Материализуем аргументы один раз: принимаем и списки, и кортежи.
        correct = tuple(correct)
        missed = tuple(missed)
        false_positive = tuple(false_positive)
        with self._lock:
            entry = self._entry(user_id)
            entry["attempts"] = int(entry.get("attempts", 0)) + 1
            entry["total_correct"] = int(entry.get("total_correct", 0)) + len(correct)
            entry["total_possible"] = int(entry.get("total_possible", 0)) + len(correct) + len(missed)
            completed: list[int] = entry.setdefault("completed", [])
            if exercise_id not in completed:
                completed.append(exercise_id)
            counters: dict[str, dict[str, int]] = entry.setdefault("conflictogens", {})

            def _bump(cid: str, field: str) -> None:
                c = counters.setdefault(str(cid), {"present": 0, "correct": 0, "false_positive": 0})
                c[field] = int(c.get(field, 0)) + 1

            for cid in correct:
                _bump(cid, "present")
                _bump(cid, "correct")
            for cid in missed:
                _bump(cid, "present")
            for cid in false_positive:
                _bump(cid, "false_positive")
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
                # Глубокая копия: обработчики не должны менять внутреннее состояние.
                "conflictogens": {
                    str(k): dict(v) for k, v in (entry.get("conflictogens") or {}).items()
                },
            }

    def completed_ids(self, user_id: int) -> set[int]:
        """Множество id упражнений, которые пользователь уже проходил хотя бы раз."""
        with self._lock:
            entry = self._data.get(str(user_id))
            if entry is None:
                return set()
            return {int(x) for x in entry.get("completed", [])}
