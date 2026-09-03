"""Регистрация всех роутеров.

Порядок включения важен: сначала специфичные обработчики, а catch-all
(фоллбек) — последним, чтобы он не перехватывал уже обработанные сообщения.
"""
from __future__ import annotations

from . import exercise, fallback, start, stats


def register_all(dp) -> None:
    dp.include_router(start.router)
    dp.include_router(exercise.router)
    dp.include_router(stats.router)
    dp.include_router(fallback.router)
