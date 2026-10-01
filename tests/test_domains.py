"""Тесты сфер жизни (доменов) и тем (субъектов): пикер тем внутри сферы.

Покрыто:
- domain_keyboard: по кнопке на сферу в порядке данных, текст «icon name»
  (без icon — просто name), callback dom:<id>, последняя строка «🏠 В меню»;
- subject_select_keyboard: по кнопке на тему (✓/• отметки) в порядке данных,
  callback sub:<id>; затем «🎲 Все темы сферы» (subsel:all), «✅ Начать
  тренировку» (subsel:start) и строка «◀️ Назад» (flow:domains) + «🏠 В меню»
  (flow:menu);
- choose_domain: сбрасывает состояние и показывает выбор сферы;
- choose_subject: известная сфера с темами → пикер тем (подпись называет сферу,
  саджится sel_domain_id/sel_subjects=[]/sel_message_id/sel_chat_id);
  неизвестная сфера → тост; известная сфера без тем → только тост;
- toggle_subject: toggle on/off перерисовывает отметки; неизвестная тема →
  тост; тема из другой сферы → тост; нет активного пикера → тост;
  «старая» клавиатура (не совпавшее sel_message_id) → тост;
- start_selected: ≥1 отмеченных тем → _begin по объединённому пулу
  (domain_id и subject_ids фиксируются, sel_* сбрасывается); 0 отмеченных →
  тост; отмеченные темы без упражнений → тост; «старая» клавиатура → тост;
- start_all_subjects: пул = все упражнения сферы, subject_ids = все темы сферы,
  sel_* сбрасывается; сфера с темами, но без упражнений → тост;
- back_to_domains: делегирует в choose_domain (сброс состояния, клавиатура сфер);
- submit: сохраняет domain_id и subject_ids в состоянии;
- next_exercise: с domain_id+subject_ids выбирает из той же сферы и по тому же
  набору тем; без subject_ids показывает выбор сферы заново; выбранные темы
  опустели (упражнения удалили из данных) — тоже выбор сферы заново.
"""
import asyncio
import random
import types

from bot.handlers import exercise as ex
from bot.keyboards import (
    CB_DOMAIN,
    CB_SUBJECT,
    CB_SUBJECT_ALL,
    CB_SUBJECT_START,
    CB_TO_DOMAINS,
    CB_TO_MENU,
    domain_keyboard,
    subject_select_keyboard,
)
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
        self.edit_markup_calls = []

    async def edit_text(self, text, reply_markup=None):
        self.edit_calls.append(("edit_text", text, reply_markup))

    async def edit_reply_markup(self, reply_markup=None):
        self.edit_markup_calls.append(("edit_reply_markup", reply_markup))


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


def test_subject_select_keyboard_structure():
    subs = [s for s in _subjects() if s.domain == "work"]  # salary, deadlines
    kb = subject_select_keyboard(subs, {"salary"})
    rows = kb.inline_keyboard
    assert len(rows) == 5  # 2 темы + «Все темы» + «Начать» + (Назад|В меню)
    # темы — в порядке данных, отметка ✓ на отмеченной, • на неотмеченной
    assert rows[0][0].text == "✓ Зарплата"
    assert rows[0][0].callback_data == f"{CB_SUBJECT}salary"
    assert rows[1][0].text == "• Сроки"
    assert rows[1][0].callback_data == f"{CB_SUBJECT}deadlines"
    assert rows[2][0].text == "🎲 Все темы сферы"
    assert rows[2][0].callback_data == CB_SUBJECT_ALL
    assert rows[3][0].text == "✅ Начать тренировку"
    assert rows[3][0].callback_data == CB_SUBJECT_START
    assert rows[4][0].text == "◀️ Назад"
    assert rows[4][0].callback_data == CB_TO_DOMAINS
    assert rows[4][1].text == "🏠 В меню"
    assert rows[4][1].callback_data == CB_TO_MENU


def test_subject_select_keyboard_marks_follow_selected_set():
    subs = [s for s in _subjects() if s.domain == "work"]  # salary, deadlines
    # ничего не отмечено — обе «•»
    kb = subject_select_keyboard(subs, set())
    assert kb.inline_keyboard[0][0].text == "• Зарплата"
    assert kb.inline_keyboard[1][0].text == "• Сроки"
    # обе отмечены — обе «✓»
    kb = subject_select_keyboard(subs, {"salary", "deadlines"})
    assert kb.inline_keyboard[0][0].text == "✓ Зарплата"
    assert kb.inline_keyboard[1][0].text == "✓ Сроки"


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


def test_choose_subject_shows_picker_and_seeds_state(tmp_path):
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
    assert "Отметь одну или несколько тем" in text
    assert kb.inline_keyboard[0][0].callback_data == f"{CB_SUBJECT}salary"
    # контекст пикера зафиксирован в состоянии
    assert state._data["sel_domain_id"] == "work"
    assert state._data["sel_subjects"] == []
    assert state._data["sel_message_id"] == 111
    assert state._data["sel_chat_id"] == 5
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


# --- toggle_subject ---


def test_toggle_subject_on_and_off_renders_marks(tmp_path):
    call = FakeCall(message=FakeMessage(), data="sub:salary")
    state = FakeState({
        "sel_domain_id": "work", "sel_subjects": [],
        "sel_message_id": 111, "sel_chat_id": 5,
    })
    run(ex.toggle_subject(
        call, state,
        subjects=_subjects(),
        subjects_by_id={s.id: s for s in _subjects()},
    ))
    # отметил: sel_subjects содержит salary, клавиатура перерисована с «✓ Зарплата»
    assert state._data["sel_subjects"] == ["salary"]
    assert len(call.message.edit_markup_calls) == 1
    kb = call.message.edit_markup_calls[0][1]
    assert kb.inline_keyboard[0][0].text == "✓ Зарплата"
    assert kb.inline_keyboard[1][0].text == "• Сроки"
    assert len(call.answered) == 1

    # второе нажатие — снял отметку
    call2 = FakeCall(message=FakeMessage(), data="sub:salary")
    run(ex.toggle_subject(
        call2, state,
        subjects=_subjects(),
        subjects_by_id={s.id: s for s in _subjects()},
    ))
    assert state._data["sel_subjects"] == []
    assert len(call2.message.edit_markup_calls) == 1
    kb2 = call2.message.edit_markup_calls[0][1]
    assert kb2.inline_keyboard[0][0].text == "• Зарплата"


def test_toggle_subject_multiple_sorted(tmp_path):
    call = FakeCall(message=FakeMessage(), data="sub:salary")
    state = FakeState({
        "sel_domain_id": "work", "sel_subjects": ["deadlines"],
        "sel_message_id": 111, "sel_chat_id": 5,
    })
    run(ex.toggle_subject(
        call, state,
        subjects=_subjects(),
        subjects_by_id={s.id: s for s in _subjects()},
    ))
    # два отмеченных — хранятся отсортированно
    assert state._data["sel_subjects"] == ["deadlines", "salary"]


def test_toggle_subject_unknown_toast_no_change(tmp_path):
    call = FakeCall(message=FakeMessage(), data="sub:ghost")
    state = FakeState({
        "sel_domain_id": "work", "sel_subjects": ["salary"],
        "sel_message_id": 111, "sel_chat_id": 5,
    })
    run(ex.toggle_subject(
        call, state,
        subjects=_subjects(),
        subjects_by_id={s.id: s for s in _subjects()},
    ))
    assert len(call.answered) == 1
    assert "недоступна" in call.answered[0][0][0]
    assert call.message.edit_markup_calls == []
    assert call.message.edit_calls == []
    assert state._data["sel_subjects"] == ["salary"]


def test_toggle_subject_other_domain_toast_no_change(tmp_path):
    # chores — тема из сферы family; пикер открыт на work
    call = FakeCall(message=FakeMessage(), data="sub:chores")
    state = FakeState({
        "sel_domain_id": "work", "sel_subjects": [],
        "sel_message_id": 111, "sel_chat_id": 5,
    })
    run(ex.toggle_subject(
        call, state,
        subjects=_subjects(),
        subjects_by_id={s.id: s for s in _subjects()},
    ))
    assert len(call.answered) == 1
    assert "другой сферы" in call.answered[0][0][0]
    assert call.message.edit_markup_calls == []
    assert state._data["sel_subjects"] == []


def test_toggle_subject_no_pending_toast(tmp_path):
    call = FakeCall(message=FakeMessage(), data="sub:salary")
    state = FakeState()  # sel_domain_id отсутствует
    run(ex.toggle_subject(
        call, state,
        subjects=_subjects(),
        subjects_by_id={s.id: s for s in _subjects()},
    ))
    assert len(call.answered) == 1
    assert "неактуально" in call.answered[0][0][0]
    assert call.message.edit_markup_calls == []
    assert state.updates == []


def test_toggle_subject_stale_binding_toast(tmp_path):
    # нажата «старая» клавиатура: sel_message_id ≠ message.id нажатия
    call = FakeCall(message=FakeMessage(), data="sub:salary")
    state = FakeState({
        "sel_domain_id": "work", "sel_subjects": [],
        "sel_message_id": 999, "sel_chat_id": 5,
    })
    run(ex.toggle_subject(
        call, state,
        subjects=_subjects(),
        subjects_by_id={s.id: s for s in _subjects()},
    ))
    assert len(call.answered) == 1
    assert "неактуально" in call.answered[0][0][0]
    assert call.message.edit_markup_calls == []
    assert state._data["sel_subjects"] == []
    assert state.updates == []


# --- start_selected ---


def test_start_selected_begins_checked_union(tmp_path, monkeypatch):
    captured = {}

    def fake_choice(seq):
        captured["pool"] = list(seq)
        return seq[0]

    monkeypatch.setattr(random, "choice", fake_choice)
    call = FakeCall(message=FakeMessage(), data=CB_SUBJECT_START)
    state = FakeState({
        "sel_domain_id": "work", "sel_subjects": ["salary", "deadlines"],
        "sel_message_id": 111, "sel_chat_id": 5,
    })
    run(ex.start_selected(
        call, state,
        domains_by_id={d.id: d for d in _domains()},
        subjects=_subjects(),
        subjects_by_id={s.id: s for s in _subjects()},
        exercises=_exercises(),
        conflictogens=_conflictogens(),
        store=Store(tmp_path / "users.json"),
    ))
    # пул — объединение упражнений обеих отмеченных тем (id 1 и 2)
    assert sorted(e.id for e in captured["pool"]) == [1, 2]
    assert state._data["domain_id"] == "work"
    assert state._data["subject_ids"] == ["salary", "deadlines"]
    assert state._data["exercise_id"] == 1
    assert state.state == ex.Train.picking
    # sel_* сброшены
    assert state._data["sel_domain_id"] is None
    assert state._data["sel_subjects"] == []
    assert state._data["sel_message_id"] is None
    assert state._data["sel_chat_id"] is None
    # сообщение отредактировано ровно один раз
    assert len(call.message.edit_calls) == 1
    assert len(call.answered) == 1


def test_start_selected_single_subject_still_works(tmp_path, monkeypatch):
    captured = {}

    def fake_choice(seq):
        captured["pool"] = list(seq)
        return seq[0]

    monkeypatch.setattr(random, "choice", fake_choice)
    call = FakeCall(message=FakeMessage(), data=CB_SUBJECT_START)
    state = FakeState({
        "sel_domain_id": "work", "sel_subjects": ["salary"],
        "sel_message_id": 111, "sel_chat_id": 5,
    })
    run(ex.start_selected(
        call, state,
        domains_by_id={d.id: d for d in _domains()},
        subjects=_subjects(),
        subjects_by_id={s.id: s for s in _subjects()},
        exercises=_exercises(),
        conflictogens=_conflictogens(),
        store=Store(tmp_path / "users.json"),
    ))
    # один отмеченный — пул только упражнения salary (id=1)
    assert [e.id for e in captured["pool"]] == [1]
    assert state._data["subject_ids"] == ["salary"]


def test_start_selected_none_checked_toast_only(tmp_path):
    call = FakeCall(message=FakeMessage(), data=CB_SUBJECT_START)
    state = FakeState({
        "sel_domain_id": "work", "sel_subjects": [],
        "sel_message_id": 111, "sel_chat_id": 5,
    })
    run(ex.start_selected(
        call, state,
        domains_by_id={d.id: d for d in _domains()},
        subjects=_subjects(),
        subjects_by_id={s.id: s for s in _subjects()},
        exercises=_exercises(),
        conflictogens=_conflictogens(),
        store=Store(tmp_path / "users.json"),
    ))
    assert len(call.answered) == 1
    assert "хотя бы одну тему" in call.answered[0][0][0]
    assert call.message.edit_calls == []
    assert state.updates == []
    assert "exercise_id" not in state._data


def test_start_selected_checked_no_exercises_toast_only(tmp_path):
    # упражнения только с subject=salary; отмечена deadlines → пустой пул
    exercises = [e for e in _exercises() if e.subject == "salary"]
    call = FakeCall(message=FakeMessage(), data=CB_SUBJECT_START)
    state = FakeState({
        "sel_domain_id": "work", "sel_subjects": ["deadlines"],
        "sel_message_id": 111, "sel_chat_id": 5,
    })
    run(ex.start_selected(
        call, state,
        domains_by_id={d.id: d for d in _domains()},
        subjects=_subjects(),
        subjects_by_id={s.id: s for s in _subjects()},
        exercises=exercises,
        conflictogens=_conflictogens(),
        store=Store(tmp_path / "users.json"),
    ))
    assert len(call.answered) == 1
    assert "В выбранных темах" in call.answered[0][0][0]
    assert "пока нет упражнений" in call.answered[0][0][0]
    assert call.message.edit_calls == []
    assert state.updates == []
    assert "exercise_id" not in state._data


def test_start_selected_stale_binding_toast(tmp_path):
    call = FakeCall(message=FakeMessage(), data=CB_SUBJECT_START)
    state = FakeState({
        "sel_domain_id": "work", "sel_subjects": ["salary"],
        "sel_message_id": 999, "sel_chat_id": 5,
    })
    run(ex.start_selected(
        call, state,
        domains_by_id={d.id: d for d in _domains()},
        subjects=_subjects(),
        subjects_by_id={s.id: s for s in _subjects()},
        exercises=_exercises(),
        conflictogens=_conflictogens(),
        store=Store(tmp_path / "users.json"),
    ))
    assert len(call.answered) == 1
    assert "неактуально" in call.answered[0][0][0]
    assert call.message.edit_calls == []
    assert state.updates == []


# --- start_all_subjects ---


def test_start_all_subjects_begins_whole_domain(tmp_path, monkeypatch):
    captured = {}

    def fake_choice(seq):
        captured["pool"] = list(seq)
        return seq[0]

    monkeypatch.setattr(random, "choice", fake_choice)
    call = FakeCall(message=FakeMessage(), data=CB_SUBJECT_ALL)
    state = FakeState({
        "sel_domain_id": "work", "sel_subjects": [],
        "sel_message_id": 111, "sel_chat_id": 5,
    })
    run(ex.start_all_subjects(
        call, state,
        domains_by_id={d.id: d for d in _domains()},
        subjects=_subjects(),
        exercises=_exercises(),
        conflictogens=_conflictogens(),
        store=Store(tmp_path / "users.json"),
    ))
    # пул — все упражнения сферы work (id 1 и 2), независимо от отметок
    assert sorted(e.id for e in captured["pool"]) == [1, 2]
    assert state._data["domain_id"] == "work"
    assert sorted(state._data["subject_ids"]) == ["deadlines", "salary"]
    assert state._data["exercise_id"] == 1
    assert state.state == ex.Train.picking
    # sel_* сброшены
    assert state._data["sel_domain_id"] is None
    assert state._data["sel_subjects"] == []
    assert state._data["sel_message_id"] is None
    assert state._data["sel_chat_id"] is None
    assert len(call.message.edit_calls) == 1
    assert len(call.answered) == 1


def test_start_all_subjects_domain_without_exercises_toast_only(tmp_path):
    # в сфере family есть тема chores, но упражнений нет
    call = FakeCall(message=FakeMessage(), data=CB_SUBJECT_ALL)
    state = FakeState({
        "sel_domain_id": "family", "sel_subjects": [],
        "sel_message_id": 111, "sel_chat_id": 5,
    })
    run(ex.start_all_subjects(
        call, state,
        domains_by_id={d.id: d for d in _domains()},
        subjects=_subjects(),
        exercises=[e for e in _exercises() if e.domain == "work"],  # только work
        conflictogens=_conflictogens(),
        store=Store(tmp_path / "users.json"),
    ))
    assert len(call.answered) == 1
    assert "Семья" in call.answered[0][0][0]  # тост называет сферу
    assert "пока нет упражнений" in call.answered[0][0][0]
    assert call.message.edit_calls == []
    assert state.updates == []
    assert "exercise_id" not in state._data


# --- back_to_domains ---


def test_back_to_domains_delegates_to_chooser(tmp_path):
    call = FakeCall(message=FakeMessage(), data=CB_TO_DOMAINS)
    state = FakeState({
        "sel_domain_id": "work", "sel_subjects": ["salary"],
        "sel_message_id": 111, "sel_chat_id": 5,
    })
    run(ex.back_to_domains(call, _domains(), state))
    assert state.cleared == 1  # choose_domain сбросил состояние
    assert len(call.message.edit_calls) == 1
    _, text, kb = call.message.edit_calls[0]
    assert text == "Выбери сферу жизни, в которой хочешь потренироваться:"
    assert kb.inline_keyboard[0][0].callback_data == f"{CB_DOMAIN}work"
    assert len(call.answered) == 1


# --- submit: domain_id сохраняется ---


def test_submit_preserves_domain_and_subjects(tmp_path):
    store = Store(tmp_path / "users.json")
    exercise = Exercise(id=1, phrase="p", conflictogens=("a",), domain="work", subject="salary")
    call = FakeCall(message=FakeMessage(message_id=111, chat_id=5), data="do:submit")
    state = FakeState({
        "exercise_id": 1, "selected": [], "domain_id": "work",
        "subject_ids": ["salary", "deadlines"],
        "message_id": 111, "chat_id": 5,
    })
    run(ex.submit(call, {1: exercise}, {"a": _conflictogens()[0]}, store, state))
    assert state.cleared == 0            # состояние НЕ сбрасывается целиком
    assert state._data["exercise_id"] is None
    assert state._data["domain_id"] == "work"
    assert state._data["subject_ids"] == ["salary", "deadlines"]
    assert len(call.message.edit_calls) == 1  # разбор ответа
    assert len(call.answered) == 1


# --- next_exercise ---


def test_next_exercise_stays_in_selected_subjects(tmp_path, monkeypatch):
    captured = {}

    def fake_choice(seq):
        captured["pool"] = list(seq)
        return seq[0]

    monkeypatch.setattr(random, "choice", fake_choice)
    call = FakeCall(message=FakeMessage(), data="flow:next")
    state = FakeState({
        "domain_id": "work", "subject_ids": ["salary", "deadlines"], "exercise_id": None,
    })
    run(ex.next_exercise(
        call, _exercises(), Store(tmp_path / "users.json"),
        _conflictogens(), _domains(), state,
    ))
    # пул — объединение упражнений обоих отмеченных тем (id 1 и 2)
    assert sorted(e.id for e in captured["pool"]) == [1, 2]
    assert state._data["domain_id"] == "work"
    assert state._data["subject_ids"] == ["salary", "deadlines"]
    assert state._data["exercise_id"] == 1
    assert len(call.message.edit_calls) == 1
    assert len(call.answered) == 1


def test_next_exercise_single_subject_union(tmp_path, monkeypatch):
    captured = {}

    def fake_choice(seq):
        captured["pool"] = list(seq)
        return seq[0]

    monkeypatch.setattr(random, "choice", fake_choice)
    call = FakeCall(message=FakeMessage(), data="flow:next")
    state = FakeState({
        "domain_id": "work", "subject_ids": ["salary"], "exercise_id": None,
    })
    run(ex.next_exercise(
        call, _exercises(), Store(tmp_path / "users.json"),
        _conflictogens(), _domains(), state,
    ))
    assert [e.id for e in captured["pool"]] == [1]  # только salary
    assert state._data["domain_id"] == "work"
    assert state._data["subject_ids"] == ["salary"]
    assert state._data["exercise_id"] == 1


def test_next_exercise_without_subjects_shows_chooser(tmp_path, monkeypatch):
    # subject_ids отсутствуют — заново показываем выбор сферы
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


def test_next_exercise_selected_pool_emptied_shows_chooser(tmp_path, monkeypatch):
    # выбранные темы зафиксированы в состоянии, но их упражнений больше нет в
    # данных (например, удалили из exercises.json) — заново показываем выбор
    # сферы, а не падаем на pick_next([])
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])
    call = FakeCall(message=FakeMessage(), data="flow:next")
    state = FakeState({
        "domain_id": "work", "subject_ids": ["salary"], "exercise_id": None,
    })
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
