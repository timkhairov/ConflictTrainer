"""Тесты «проводки» обработчиков: параметры должны покрываться builtin-аргументами
и ключами workflow_data (см. bot/main.py), а фоллбек — регистрироваться последним.
"""
import inspect

from bot.handlers import exercise, fallback, register_all, start, stats

BUILTINS = {"message", "call", "state"}
PROVIDED = {"conflictogens", "conflictogens_by_id", "exercises", "exercises_by_id", "store"}


def _handler_fns(router):
    fns = []
    for grp in (router.message, router.callback_query):
        for h in getattr(grp, "handlers", []):
            fns.append(h.callback)
    return fns


def _all_routers():
    return [start.router, exercise.router, stats.router, fallback.router]


def test_handler_params_are_provided():
    missing = []
    for router in _all_routers():
        for fn in _handler_fns(router):
            for p in inspect.signature(fn).parameters:
                if p in BUILTINS:
                    continue
                if p not in PROVIDED:
                    missing.append(f"{fn.__module__}.{fn.__name__}:{p}")
    assert not missing, "MISSING -> " + "; ".join(missing)


def test_each_router_has_handlers():
    for router in _all_routers():
        assert _handler_fns(router), f"router {router.name!r} has no handlers"


def test_fallback_registered_last():
    class FakeDP:
        def __init__(self):
            self.order = []

        def include_router(self, router):
            self.order.append(router.name)

    dp = FakeDP()
    register_all(dp)
    assert dp.order[-1] == "fallback"
    assert dp.order == ["start", "exercise", "stats", "fallback"]
