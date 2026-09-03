"""Проверка ответа пользователя на упражнение."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Exercise


@dataclass(frozen=True)
class AttemptResult:
    """Разбивка ответа пользователя на три категории."""

    exercise_id: int
    correct: tuple[str, ...]        # отметил и это действительно есть
    missed: tuple[str, ...]         # есть в фразе, но пользователь пропустил
    false_positive: tuple[str, ...]  # отметил, но в фразе такого паттерна нет
    score_num: int                  # количество правильных
    score_den: int                  # всего верных конфликтогенов в задаче

    @property
    def perfect(self) -> bool:
        return not self.missed and not self.false_positive


def evaluate(exercise: Exercise, selected: list[str]) -> AttemptResult:
    """Сравнивает выбранные пользователем id с верным набором.

    Порядок в результатах сохраняется по порядку «ответа» (для correct/missed)
    и по порядку выбора (для false_positive).
    """
    answer = set(exercise.conflictogens)
    sel = set(selected)

    correct = tuple(c for c in exercise.conflictogens if c in sel)
    missed = tuple(c for c in exercise.conflictogens if c not in sel)
    false_positive = tuple(c for c in selected if c not in answer)

    return AttemptResult(
        exercise_id=exercise.id,
        correct=correct,
        missed=missed,
        false_positive=false_positive,
        score_num=len(correct),
        score_den=len(exercise.conflictogens),
    )
