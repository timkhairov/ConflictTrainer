"""Модели доменных данных.

Используются неизменяемые (frozen) dataclass, чтобы случайно не переопределить
узел данных в процессе обработки.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Conflictogen:
    """Один конфликтоген (элемент меню)."""

    id: str          # стабильный ключ (латиницей), используется в данных и callback'ах
    name: str        # подпись кнопки, которую видит пользователь
    description: str = ""  # короткое пояснение (справка, разбор ответа)


@dataclass(frozen=True)
class Domain:
    """Сфера жизни (группа упражнений)."""

    id: str          # стабильный ключ (латиницей), используется в данных и callback'ах
    name: str        # подпись кнопки, которую видит пользователь
    icon: str = ""   # необязательный эмодзи-префикс на кнопке


@dataclass(frozen=True)
class Subject:
    """Тема (субъект) внутри сферы — второй уровень выбора."""

    id: str          # стабильный ключ (латиницей), используется в данных и callback'ах
    name: str        # подпись кнопки, которую видит пользователь
    domain: str      # id сферы (domains.json), к которой относится тема


@dataclass(frozen=True)
class Exercise:
    """Упражнение: конфликтная фраза + набор верных конфликтогенов."""

    id: int
    phrase: str
    conflictogens: tuple[str, ...]  # id верных конфликтогенов
    domain: str                     # id сферы жизни (domains.json), например "work"
    subject: str                    # id темы (subjects.json), например "salary"
    note: str = ""                  # необязательное пояснение к разбору
