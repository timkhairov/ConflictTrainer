"""Тесты сфер жизни (доменов) и тем (субъектов): двухуровневый выбор.

Покрыто:
- domain_keyboard: по кнопке на сферу в порядке данных, текст «icon name»
  (без icon — просто name), callback dom:<id>, последняя строка «🏠 В меню»;
- subject_keyboard: по кнопке на тему в порядке данных, callback sub:<id>,
  последняя строка «🏠 В меню»;
- choose_domain: сбрасывает состояние и показывает выбор сферы;
- choose_subject: известная сфера с темами → показывает выбор темы;
  неизвестная сфера → тост; известная сфера без тем → только тост;
- start_training: известная тема с упражнениями → _begin по подмножеству
  (domain_id и subject_id фиксируются в состоянии); пустая тема → только тост;
  неизвестная тема → тост;
- submit: сохраняет domain_id и subject_id в состоянии;
- next_exercise: с domain_id+subject_id выбирает из той же сферы и темы;
  без subject_id показывает выбор сферы заново; тема опустела (упражнения
  удалили из данных) — тоже выбор сферы заново.
"""
import asyncio
import random
import types

from bot.handlers import exercise as ex
from bot.keyboards import CB_DOMAIN, CB_SUBJECT, CB_TO_MENU, domain_keyboard, subject_keyboard
from bot.models import Conflictogen, Domain, Exercise, Subject
from bot.store import Store


def run(coro):
    return asyncio.run(coro)


class FakeState:
    def __init__(self, data=None):
        self._data = dict(data or {})
        self.updates = []
        self.cleared = 0
        self.state = None

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kw):
        self._data.update(kw)
        self.updates.append(kw)

    async def set_state(self, s):
        self.state = s

    async def clear(self):
        self.cleared += 1


class FakeMessage:
    def __init__(self, message_id=111, chat_id=5):
        self.message_id = message_id
        self.chat = types.SimpleNamespace(id=chat_id, type="private")
        self.edit_calls = []

    async def edit_text(self, text, reply_markup=None):
        self.edit_calls.append(("edit_text", text, reply_markup))


class FakeCall:
    def __init__(self, message=None, data="dom:work", from_user_id=1):
        self.message = message
        self.data = data
        self.from_user = types.SimpleNamespace(id=from_user_id)
        self.answered = []

    async def answer(self, *args, **kwargs):
        self.answered.append((args, kwargs))


def _domains():
    return [
        Domain(id="work", name="Работа", icon="💼"),
        Domain(id="family", name="Семья", icon=""),  # без иконки
    ]


def _subjects():
    return [
        Subject(id="salary", name="Зарплата", domain="work"),
        Subject(id="deadlines", name="Сроки", domain="work"),
        Subject(id="chores", name="Быт", domain="family"),
    ]


def _exercises():
    return [
        Exercise(id=1, phrase="w1", conflictogens=("a",), domain="work", subject="salary"),
        Exercise(id=2, phrase="w2", conflictogens=("a",), domain="work", subject="deadlines"),
        Exercise(id=3, phrase="f1", conflictogens=("a",), domain="family", subject="chores"),
    ]


def _conflictogens():
    return [Conflictogen(id="a", name="A", description="")]


# --- domain_keyboard ---


def test_domain_keyboard_structure():
    kb = domain_keyboard(_domains())
    rows = kb.inline_keyboard
    assert len(rows) == 3  # две сферы + «В меню»
    assert rows[0][0].text == "💼 Работа"
    assert rows[0][0].callback_data == f"{CB_DOMAIN}work"
    assert rows[1][0].text == "Семья"  # без icon — просто название
    assert rows[1][0].callback_data == f"{CB_DOMAIN}family"
    assert rows[2][0].text == "🏠 В меню"
    assert rows[2][0].callback_data == CB_TO_MENU


def test_subject_keyboard_structure():
    subs = [s for s in _subjects() if s.domain == "work"]
    kb = subject_keyboard(subs)
    rows = kb.inline_keyboard
    assert len(rows) == 3  # две темы + «В меню»
    assert rows[0][0].text == "Зарплата"
    assert rows[0][0].callback_data == f"{CB_SUBJECT}salary"
    assert rows[1][0].text == "Сроки"
    assert rows[1][0].callback_data == f"{CB_SUBJECT}deadlines"
    assert rows[2][0].text == "🏠 В меню"
    assert rows[2][0].callback_data == CB_TO_MENU


# --- choose_domain ---


def test_choose_domain_clears_state_and_edits():
    call = FakeCall(message=FakeMessage(), data="menu:start_training")
    state = FakeState({"exercise_id": 1})
    run(ex.choose_domain(call, _domains(), state))
    assert state.cleared == 1
    assert len(call.message.edit_calls) == 1
    _, text, kb = call.message.edit_calls[0]
    assert text == "Выбери сферу жизни, в которой хочешь потренироваться:"
    assert kb.inline_keyboard[0][0].callback_data == f"{CB_DOMAIN}work"
    assert len(call.answered) == 1


# --- choose_subject ---


def test_choose_subject_shows_subject_keyboard(tmp_path):
    call = FakeCall(message=FakeMessage(), data="dom:work")
    state = FakeState()
    run(ex.choose_subject(
        call, state,
        domains_by_id={d.id: d for d in _domains()},
        subjects=_subjects(),
    ))
    assert len(call.message.edit_calls) == 1
    _, text, kb = call.message.edit_calls[0]
    assert "Работа" in text
    assert kb.inline_keyboard[0][0].callback_data == f"{CB_SUBJECT}salary"
    assert len(call.answered) == 1


def test_choose_subject_unknown_domain_toast_only(tmp_path):
    call = FakeCall(message=FakeMessage(), data="dom:ghost")
    state = FakeState()
    run(ex.choose_subject(
        call, state,
        domains_by_id={d.id: d for d in _domains()},
        subjects=_subjects(),
    ))
    assert len(call.answered) == 1
    assert "недоступна" in call.answered[0][0][0]
    assert call.message.edit_calls == []
    assert state.updates == []


def test_choose_subject_domain_without_subjects_toast_only():
    # известная сфера, в которой нет ни одной темы → только тост,
    # сообщение и состояние не трогаем
    call = FakeCall(message=FakeMessage(), data="dom:family")
    state = FakeState({"exercise_id": 7})
    subjects = [s for s in _subjects() if s.domain == "work"]  # в family тем нет
    run(ex.choose_subject(
        call, state,
        domains_by_id={d.id: d for d in _domains()},
        subjects=subjects,
    ))
    assert len(call.answered) == 1
    assert "Семья" in call.answered[0][0][0]  # тост называет сферу
    assert "пока нет тем" in call.answered[0][0][0]
    assert call.message.edit_calls == []
    assert state.updates == []
    assert state._data == {"exercise_id": 7}


# --- start_training ---


def test_start_training_begins_subject_subset(tmp_path, monkeypatch):
    captured = {}

    def fake_choice(seq):
        captured["pool"] = list(seq)
        return seq[0]

    monkeypatch.setattr(random, "choice", fake_choice)
    call = FakeCall(message=FakeMessage(), data="sub:salary")
    state = FakeState()
    run(ex.start_training(
        call, state,
        subjects_by_id={s.id: s for s in _subjects()},
        exercises=_exercises(),
        conflictogens=_conflictogens(),
        store=Store(tmp_path / "users.json"),
    ))
    # пул — только упражнения с subject=salary (id=1)
    assert [e.id for e in captured["pool"]] == [1]
    assert state._data["domain_id"] == "work"
    assert state._data["subject_id"] == "salary"
    assert state._data["exercise_id"] == 1
    assert state.state == ex.Train.picking
    assert len(call.message.edit_calls) == 1
    assert len(call.answered) == 1


def test_start_training_empty_subject_toast_only(tmp_path):
    # упражнения только с subject=salary; sub:deadlines → пустой пул
    exercises = [e for e in _exercises() if e.subject == "salary"]
    call = FakeCall(message=FakeMessage(), data="sub:deadlines")
    state = FakeState({"exercise_id": 7})
    run(ex.start_training(
        call, state,
        subjects_by_id={s.id: s for s in _subjects()},
        exercises=exercises,
        conflictogens=_conflictogens(),
        store=Store(tmp_path / "users.json"),
    ))
    assert len(call.answered) == 1
    assert "Сроки" in call.answered[0][0][0]  # тост называет тему
    assert "пока нет упражнений" in call.answered[0][0][0]
    assert call.message.edit_calls == []
    assert state.updates == []
    assert state._data == {"exercise_id": 7}


def test_start_training_unknown_subject_toast_only(tmp_path):
    call = FakeCall(message=FakeMessage(), data="sub:ghost")
    state = FakeState()
    run(ex.start_training(
        call, state,
        subjects_by_id={s.id: s for s in _subjects()},
        exercises=_exercises(),
        conflictogens=_conflictogens(),
        store=Store(tmp_path / "users.json"),
    ))
    assert len(call.answered) == 1
    assert "недоступна" in call.answered[0][0][0]
    assert call.message.edit_calls == []
    assert state.updates == []


# --- submit: domain_id сохраняется ---


def test_submit_preserves_domain_and_subject(tmp_path):
    store = Store(tmp_path / "users.json")
    exercise = Exercise(id=1, phrase="p", conflictogens=("a",), domain="work", subject="salary")
    call = FakeCall(message=FakeMessage(message_id=111, chat_id=5), data="do:submit")
    state = FakeState({
        "exercise_id": 1, "selected": [], "domain_id": "work", "subject_id": "salary",
        "message_id": 111, "chat_id": 5,
    })
    run(ex.submit(call, {1: exercise}, {"a": _conflictogens()[0]}, store, state))
    assert state.cleared == 0            # состояние НЕ сбрасывается целиком
    assert state._data["exercise_id"] is None
    assert state._data["domain_id"] == "work"
    assert state._data["subject_id"] == "salary"
    assert len(call.message.edit_calls) == 1  # разбор ответа
    assert len(call.answered) == 1


# --- next_exercise ---


def test_next_exercise_stays_in_subject(tmp_path, monkeypatch):
    captured = {}

    def fake_choice(seq):
        captured["pool"] = list(seq)
        return seq[0]

    monkeypatch.setattr(random, "choice", fake_choice)
    call = FakeCall(message=FakeMessage(), data="flow:next")
    state = FakeState({"domain_id": "work", "subject_id": "salary", "exercise_id": None})
    run(ex.next_exercise(
        call, _exercises(), Store(tmp_path / "users.json"),
        _conflictogens(), _domains(), state,
    ))
    assert [e.id for e in captured["pool"]] == [1]  # только salary
    assert state._data["domain_id"] == "work"
    assert state._data["subject_id"] == "salary"
    assert state._data["exercise_id"] == 1
    assert len(call.message.edit_calls) == 1
    assert len(call.answered) == 1


def test_next_exercise_without_subject_shows_chooser(tmp_path, monkeypatch):
    # subject_id отсутствует — заново показываем выбор сферы
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    call = FakeCall(message=FakeMessage(), data="flow:next")
    state = FakeState({"domain_id": "work", "exercise_id": None})
    run(ex.next_exercise(
        call, _exercises(), Store(tmp_path / "users.json"),
        _conflictogens(), _domains(), state,
    ))
    assert len(call.message.edit_calls) == 1
    _, text, kb = call.message.edit_calls[0]
    assert text == "Выбери сферу жизни, в которой хочешь потренироваться:"
    assert kb.inline_keyboard[0][0].callback_data == f"{CB_DOMAIN}work"
    assert state.cleared == 1  # choose_domain сбросил состояние
    assert len(call.answered) == 1


def test_next_exercise_subject_pool_emptied_shows_chooser(tmp_path, monkeypatch):
    # тема зафиксирована в состоянии, но её упражнений больше нет в данных
    # (например, удалили из exercises.json) — заново показываем выбор сферы,
    # а не падаем на pick_next([])
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    call = FakeCall(message=FakeMessage(), data="flow:next")
    state = FakeState({"domain_id": "work", "subject_id": "salary", "exercise_id": None})
    exercises = [e for e in _exercises() if e.subject != "salary"]  # пул salary пуст
    run(ex.next_exercise(
        call, exercises, Store(tmp_path / "users.json"),
        _conflictogens(), _domains(), state,
    ))
    assert len(call.message.edit_calls) == 1
    _, text, kb = call.message.edit_calls[0]
    assert text == "Выбери сферу жизни, в которой хочешь потренироваться:"
    assert kb.inline_keyboard[0][0].callback_data == f"{CB_DOMAIN}work"
    assert state.cleared == 1
    assert len(call.answered) == 1
