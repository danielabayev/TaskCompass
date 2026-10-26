"""Layer 2, daily version: the interview code around the model, with scripted
model answers. One test per test task in tests/behavior/scenarios.py, plus
the failure paths from the build plan ("API failures")."""

import pytest
from sqlalchemy import select

from task_compass.errors import FlowError
from task_compass.interview.service import InterviewService, is_pending, open_turn
from task_compass.llm.gateway import CallFailed, InvalidAnswer, LLMError
from task_compass.models import InterviewTurn, LlmCall, Task
from tests.helpers import GOOD_CARD, bad, judged, make_gateway, question


@pytest.fixture
def setup(session_factory):
    fake, gateway = make_gateway(session_factory)
    return fake, InterviewService(gateway, session_factory), session_factory


def load(factory, task_id) -> Task:
    s = factory()
    task = s.get(Task, task_id)
    _ = task.turns, task.category  # load relations before closing
    s.close()
    return task


def test_1_activity_is_not_a_deliverable(setup):
    fake, svc, factory = setup
    fake.queue("judge", judged(type_key="errands"))
    fake.queue("ask", question("מה יהיה שונה במחסן כשתסיים?"))
    task_id = svc.start("לסדר את המחסן")
    task = load(factory, task_id)
    assert task.category.key == "errands"  # type suggested on the first turn
    assert open_turn(task).field == "deliverable"

    fake.queue("judge", judged(type_key="errands", deliverable="לעבוד על המחסן",
                               deliverable_verdict=bad("זו פעילות, לא תוצר")))
    fake.queue("ask", question("איך ייראה המחסן כשהמשימה גמורה?"))
    svc.answer(task_id, "לעבוד על המחסן")
    task = load(factory, task_id)
    assert task.verdicts["deliverable"]["status"] == "fail"
    assert open_turn(task).field == "deliverable"
    assert "deliverable" in fake.calls[-1]["user"]  # the question targets the failing field


def test_2_vague_done_test_is_rejected_and_asked_about(setup):
    fake, svc, factory = setup
    fake.queue("judge", judged(type_key="write", deliverable="דוח רבעוני בקובץ PDF"))
    fake.queue("ask", question("איך תדע שהדוח גמור?"))
    task_id = svc.start("לטפל בדוח")
    assert open_turn(load(factory, task_id)).field == "done_tests"

    fake.queue("judge", judged(type_key="write", deliverable="דוח רבעוני בקובץ PDF",
                               done_tests=["הדוח טוב"], done_tests_verdict=bad("לא שאלת כן/לא")))
    fake.queue("ask", question("איזו בדיקת כן/לא תראה שהדוח מוכן?"))
    svc.answer(task_id, "הדוח טוב")
    task = load(factory, task_id)
    assert task.verdicts["done_tests"] == {"status": "fail", "reason": "לא שאלת כן/לא"}
    assert open_turn(task).field == "done_tests"


def test_3_enough_does_not_close_and_shows_what_is_missing(setup):
    fake, svc, factory = setup
    fake.queue("judge", judged(type_key="learn"))
    fake.queue("ask", question())
    task_id = svc.start("ללמוד SQL")
    fake.queue("judge", judged(type_key="learn", deliverable="פתרון 3 תרגילי JOIN"))
    fake.queue("ask", question("איך תבדוק שאתה יודע?"))
    svc.answer(task_id, "פתרון 3 תרגילי JOIN")

    fake.queue("ask", question("מה לא נכלל?"))  # no judge call is queued: "enough" skips it
    svc.answer(task_id, "מספיק!")
    task = load(factory, task_id)
    assert task.status == "interview"
    turn = open_turn(task)
    assert turn.round_no == 3
    assert "מבחני סיום" in turn.note and "צעד ראשון" in turn.note
    assert [c["purpose"] for c in fake.calls].count("judge") == 2


def test_4_good_answers_reach_estimation(setup):
    fake, svc, factory = setup
    fake.queue("judge", judged(type_key="write", deliverable=GOOD_CARD["deliverable"]))
    fake.queue("ask", question())
    task_id = svc.start("לכתוב מייל למנהל")
    fake.queue("judge", judged(**GOOD_CARD))
    svc.answer(task_id, "מבחן: המייל נשלח. לא כולל פגישה. צעד ראשון: לפתוח טיוטה")
    task = load(factory, task_id)
    assert task.status == "estimate"
    assert open_turn(task) is None and len(task.turns) == 1


def test_5_twelve_rounds_without_a_ready_card_is_stuck(setup):
    fake, svc, factory = setup
    fake.queue("judge", *[judged(type_key="build", deliverable="מערכת", deliverable_verdict=bad())] * 13)
    fake.queue("ask", *[question()] * 12)
    task_id = svc.start("לבנות מערכת CRM")
    for i in range(12):
        svc.answer(task_id, f"משהו כללי {i}")
    task = load(factory, task_id)
    assert task.status == "stuck"
    assert len(task.turns) == 12 and all(t.answer for t in task.turns)

    child_id = None
    fake.queue("judge", judged(type_key="build"))
    fake.queue("ask", question())
    child_id = svc.resolve_stuck(task_id, "split", "מסך כניסה בלבד")
    parent, child = load(factory, task_id), load(factory, child_id)
    assert parent.status == "closed" and parent.outcome == "split"
    assert parent.deliverable == "מערכת"  # kept as history, but never marked ready
    assert child.parent_id == task_id and child.status == "interview"


def test_5b_investigation_gets_a_default_opening(setup):
    fake, svc, factory = setup
    fake.queue("judge", *[judged(type_key="build")] * 13)
    fake.queue("ask", *[question()] * 12)
    task_id = svc.start("לבנות מערכת CRM")
    for i in range(12):
        svc.answer(task_id, "לא יודע")
    fake.queue("judge", judged(type_key="learn"))
    fake.queue("ask", question())
    child_id = svc.resolve_stuck(task_id, "investigate", "  ")
    assert load(factory, child_id).opening_text.endswith("לבנות מערכת CRM")
    assert load(factory, task_id).outcome == "investigate"


def test_6_decide_type_is_passed_to_the_judge(setup):
    fake, svc, factory = setup
    fake.queue("judge", judged(type_key="decide"))
    fake.queue("ask", question())
    task_id = svc.start("להחליט איזה מחשב נייד לקנות")
    assert load(factory, task_id).category.key == "decide"
    fake.queue("judge", judged(type_key="decide", deliverable="החלטה", done_tests=["חשבתי על זה"],
                               done_tests_verdict=bad("בהחלטה צריך פתק עם הבחירה והנימוקים")))
    fake.queue("ask", question())
    svc.answer(task_id, "חשבתי על זה")
    assert '"type_key": "decide"' in fake.calls[-2]["user"]
    assert load(factory, task_id).verdicts["done_tests"]["status"] == "fail"


def test_7_type_change_midway_rejudges_and_replaces_the_question(setup):
    fake, svc, factory = setup
    fake.queue("judge", judged(type_key="build", deliverable="סקריפט גיבוי", done_tests=["הסקריפט רץ?"]))
    fake.queue("ask", question("מה לא בכלל?"))
    task_id = svc.start("סקריפט גיבוי")
    fake.queue("judge", judged(type_key="fix", deliverable="סקריפט גיבוי", done_tests=["הסקריפט רץ?"],
                               done_tests_verdict=bad("בתיקון צריך לבדוק שהתקלה לא חוזרת")))
    fake.queue("ask", question("איך תבדוק שהתקלה לא חוזרת?"))
    svc.change_type(task_id, "fix")
    task = load(factory, task_id)
    assert task.category.key == "fix"
    assert len(task.turns) == 1 and open_turn(task).field == "done_tests"
    assert open_turn(task).round_no == 1  # a type change is not a round
    assert "שיניתי את סוג המשימה" in fake.calls[-2]["user"]


def test_type_is_not_changed_by_the_model_once_set(setup):
    fake, svc, factory = setup
    fake.queue("judge", judged(type_key="write"), judged(type_key="build"))
    fake.queue("ask", question(), question())
    task_id = svc.start("לכתוב מייל")
    svc.answer(task_id, "בעצם זה פרויקט")
    assert load(factory, task_id).category.key == "write"


def test_unknown_type_from_model_fails_the_type_field(setup):
    fake, svc, factory = setup
    fake.queue("judge", judged(type_key="cooking"))
    fake.queue("ask", question())
    task_id = svc.start("להכין ארוחה")
    task = load(factory, task_id)
    assert task.category is None and open_turn(task).field == "type"


def test_change_to_inactive_type_is_rejected(setup):
    fake, svc, factory = setup
    fake.queue("judge", judged())
    fake.queue("ask", question())
    task_id = svc.start("משהו")
    with pytest.raises(FlowError):
        svc.change_type(task_id, "nonexistent")


# --- API failures -------------------------------------------------------------

def test_answer_is_saved_before_the_call_and_retry_continues(setup):
    fake, svc, factory = setup
    fake.queue("judge", judged())
    fake.queue("ask", question())
    task_id = svc.start("לכתוב מייל")
    fake.queue("judge", CallFailed("APIConnectionError"))
    with pytest.raises(LLMError) as err:
        svc.answer(task_id, "מייל למנהל")
    assert "נשמרה" in err.value.message_he
    task = load(factory, task_id)
    assert task.turns[0].answer == "מייל למנהל" and is_pending(task)

    fake.queue("judge", judged(deliverable="מייל למנהל"))
    fake.queue("ask", question())
    svc.retry(task_id)
    task = load(factory, task_id)
    assert not is_pending(task) and len(task.turns) == 2


def test_invalid_answer_gets_one_repair(setup):
    fake, svc, factory = setup
    fake.queue("judge", judged())
    fake.queue("ask", question("מה התוצר? ומה המבחן?"), question("מה התוצר?"))
    task_id = svc.start("משהו")
    assert open_turn(load(factory, task_id)).question == "מה התוצר?"
    assert "previous answer was rejected" in fake.calls[-1]["user"]


def test_second_invalid_answer_fails_without_a_partial_card(setup):
    fake, svc, factory = setup
    fake.queue("judge", InvalidAnswer("bad"), InvalidAnswer("bad"))
    with pytest.raises(LLMError):
        svc.start("משהו")
    s = factory()
    task = s.scalars(select(Task)).one()
    assert is_pending(task) and task.deliverable is None and task.status == "interview"
    assert s.scalar(select(LlmCall).where(LlmCall.success.is_(False)).limit(1)) is not None
    s.close()


def test_every_call_is_logged_with_tokens_and_cost(setup):
    fake, svc, factory = setup
    fake.queue("judge", judged())
    fake.queue("ask", question())
    svc.start("משהו")
    s = factory()
    calls = s.scalars(select(LlmCall).order_by(LlmCall.id)).all()
    assert [(c.purpose, c.model, c.success) for c in calls] == [
        ("judge", "claude-haiku-5-5", True), ("ask", "claude-opus-5-5", True)]
    assert float(calls[1].cost_usd) == pytest.approx((1000 * 4 + 200 * 20) / 1e6)
    s.close()


def test_cost_cap_blocks_the_call(session_factory):
    fake, gateway = make_gateway(session_factory, cap=0.0)
    svc = InterviewService(gateway, session_factory)
    with pytest.raises(LLMError) as err:
        svc.start("משהו")
    assert "תקרת" in err.value.message_he
    assert fake.calls == []


def test_round_count_comes_from_the_table(setup):
    fake, svc, factory = setup
    fake.queue("judge", *[judged()] * 3)
    fake.queue("ask", *[question()] * 3)
    task_id = svc.start("משהו")
    svc.answer(task_id, "א")
    # A fresh service (like a server restart) continues from the database.
    svc2 = InterviewService(svc.gateway, factory)
    svc2.answer(task_id, "ב")
    s = factory()
    assert s.scalars(select(InterviewTurn.round_no).where(InterviewTurn.task_id == task_id)).all() == [1, 2, 3]
    s.close()


def test_answer_on_a_finished_interview_is_rejected(setup):
    fake, svc, factory = setup
    fake.queue("judge", judged(**GOOD_CARD))
    task_id = svc.start("לכתוב מייל")
    with pytest.raises(FlowError):
        svc.answer(task_id, "עוד משהו")
