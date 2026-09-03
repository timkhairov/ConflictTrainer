"""Точка входа: инициализация бота, диспетчера, данных и запуск polling.

Запуск из корня проекта:
    python -m bot.main
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types.error_event import ErrorEvent

from .config import DATA_DIR, STORAGE_DIR, bot_token
from .data_loader import DataError, load_all
from .handlers import register_all
from .handlers.common import ERROR_ANSWER
from .store import Store

log = logging.getLogger(__name__)


async def on_error(event: ErrorEvent) -> bool:
    """Глобальный обработчик ошибок: логируем и вежливо отвечаем пользователю.

    Пользователь никогда не видит «голый» traceback — максимум короткое
    извинение. Ответ может не доставиться (например, callback уже был
    отвечен обработчиком) — это не ошибка, просто логируем и продолжаем.
    """
    log.error(
        "Необработанная ошибка (update=%s): %s",
        type(event.update).__name__, event.exception,
        exc_info=event.exception,
    )
    # ErrorEvent.update — это «обёртка» aiogram.types.Update (не CallbackQuery/Message),
    # поэтому достаем нужный объект из Update и отвечаем через него. Update
    # перемонтирован с ботом, так что .answer() доступен.
    update = event.update
    try:
        if update.callback_query is not None:
            await update.callback_query.answer(ERROR_ANSWER)
        elif update.message is not None:
            await update.message.answer(ERROR_ANSWER)
    except Exception:
        log.debug("Не удалось ответить пользователю на ошибку", exc_info=True)
    return True


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # 1) Загружаем данные (при ошибке — понятное сообщение и выход)
    try:
        conflictogens, exercises = load_all(DATA_DIR)
    except DataError as e:
        log.error("Ошибка данных:\n%s", e)
        raise SystemExit(1)
    log.info(
        "Загружено конфликтогенов: %d, упражнений: %d",
        len(conflictogens), len(exercises),
    )

    store = Store(STORAGE_DIR / "users.json")

    # 2) Бот и диспетчер
    try:
        token = bot_token()
    except RuntimeError as e:
        log.error("%s", e)
        raise SystemExit(1)
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.errors.register(on_error)

    # 3) Передаём данные в обработчики через workflow_data
    dp["conflictogens"] = conflictogens
    dp["conflictogens_by_id"] = {c.id: c for c in conflictogens}
    dp["exercises"] = exercises
    dp["exercises_by_id"] = {e.id: e for e in exercises}
    dp["store"] = store

    # 4) Подключаем роутеры и стартуем
    register_all(dp)
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Бот запущен. Ожидание сообщений…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
