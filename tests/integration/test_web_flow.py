"""The whole path through the web app, with a scripted model."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from task_compass.config import Settings
from task_compass.models import Task
from task_compass.web import create_app
from task_compass.wiring import build_services
from tests.helpers import GOOD_CARD, judged, proposal, question
from task_compass.llm.fake import FakeClient
from task_compass.llm.gateway import CallFailed


@pytest.fixture
def env(session_factory):
    fake = FakeClient()
    services = build_services(fake, session_factory, Settings(anthropic_api_key="", monthly_cost_cap_usd=10))
    app = create_app(services)
    return fake, app.test_client(), session_factory


HX = {"HX-Request": "true"}


def task_row(factory, task_id=1) -> Task:
    s = factory()
    t = s.get(Task, task_id)
    _ = t.checkpoints, t.retro, t.category
    s.close()
    return t


def shift_start(factory, minutes, task_id=1):
    s = factory()
    t = s.get(Task, task_id)
    t.started_at = t.started_at - timedelta(minutes=minutes)
    s.commit()
    s.close()


def to_planned(fake, client, factory, blind=30, model=(20, 15), binding=40):
    fake.queue("judge", judged(type_key="write", deliverable=GOOD_CARD["deliverable"]))
    fake.queue("ask", question("מה המבחן?"))
    r = client.post("/tasks", data={"opening": "לכתוב מייל למנהל"})
    assert r.status_code == 302
    fake.queue("judge", judged(**GOOD_CARD))
    client.post("/tasks/1/answer", data={"answer": "הכול"}, headers=HX)
    fake.queue("propose", proposal(*model))
    client.post("/tasks/1/blind", data={"minutes": str(blind)}, headers=HX)
    client.post("/tasks/1/binding", data={"minutes": str(binding)}, headers=HX)
    assert task_row(factory).status == "planned"


def test_pages_render_rtl_hebrew(env):
    fake, client, factory = env
    for url in ("/", "/history", "/spend"):
        r = client.get(url)
        assert r.status_code == 200
        assert 'dir="rtl"' in r.text and 'lang="he"' in r.text


def test_interview_screen_shows_question_card_and_marks(env):
    fake, client, factory = env
    fake.queue("judge", judged(type_key="errands", deliverable="לעבוד על המחסן", deliverable_verdict=None))
    fake.queue("ask", question("איך ייראה המחסן בסוף?", "למשל: מדפים מסודרים"))
    client.post("/tasks", data={"opening": "לסדר את המחסן"})
    r = client.get("/tasks/1")
    assert "איך ייראה המחסן בסוף?" in r.text and "למשל: מדפים מסודרים" in r.text
    assert "כרטיס המשימה" in r.text and 'class="mark pass"' in r.text and 'class="mark unchecked"' in r.text
    assert "סבב 1 מתוך 12" in r.text


def test_happy_path_on_time_closes_with_short_retro(env):
    fake, client, factory = env
    to_planned(fake, client, factory, blind=30, model=(20, 15), binding=40)
    t = task_row(factory)
    assert (t.blind_estimate_min, t.model_estimate_min, t.corrected_estimate_min) == (30, 35, 30)
    assert t.calibration_source == "none" and not t.needed_clarification
    client.post("/tasks/1/start", headers=HX)
    shift_start(factory, 39)
    r = client.post("/tasks/1/finish", headers=HX)
    t = task_row(factory)
    assert t.status == "closed" and t.actual_min == 40 and t.retro.kind == "short"
    assert "בלי שאלות" in r.text


def test_blind_estimate_is_locked_before_the_proposal_is_shown(env):
    fake, client, factory = env
    fake.queue("judge", judged(**GOOD_CARD))
    client.post("/tasks", data={"opening": "מייל"})
    r = client.get("/tasks/1")
    assert "הצעת המודל" not in r.text  # nothing about the model's number yet
    fake.queue("propose", CallFailed("overloaded"))
    r = client.post("/tasks/1/blind", data={"minutes": "30"}, headers=HX)
    assert "לנסות שוב" in r.text
    assert task_row(factory).blind_estimate_min == 30  # saved before the call
    r = client.post("/tasks/1/blind", data={"minutes": "50"}, headers=HX)
    assert task_row(factory).blind_estimate_min == 30
    assert "כבר נשמרה" in r.text or "לא מתאימה" in r.text


def test_gap_triggers_clarification_then_binding(env):
    fake, client, factory = env
    fake.queue("judge", judged(**GOOD_CARD))
    client.post("/tasks", data={"opening": "מייל"})
    fake.queue("propose", proposal(40, 30))  # 70 vs 30
    r = client.post("/tasks/1/blind", data={"minutes": "30"}, headers=HX)
    assert "פער של פי 2" in r.text
    r = client.post("/tasks/1/binding", data={"minutes": "30"}, headers=HX)
    assert "לא מתאימה" in r.text  # cannot skip the clarification
    fake.queue("propose", proposal(20, 20))
    r = client.post("/tasks/1/clarify", data={"clarification": "רק טיוטה אחת"}, headers=HX)
    t = task_row(factory)
    assert t.clarification_note == "רק טיוטה אחת" and t.model_estimate_min == 40 and t.needed_clarification
    assert "ההערכה המחייבת" in r.text
    assert "רק טיוטה אחת" in fake.calls[-1]["user"]


def test_no_gap_goes_straight_to_binding(env):
    fake, client, factory = env
    fake.queue("judge", judged(**GOOD_CARD))
    client.post("/tasks", data={"opening": "מייל"})
    fake.queue("propose", proposal(25, 25))  # 50 vs 30
    r = client.post("/tasks/1/blind", data={"minutes": "30"}, headers=HX)
    assert "פער של פי 2" not in r.text and "ההערכה המחייבת" in r.text


def test_timer_survives_reload_and_checkpoint_appears_when_time_is_up(env):
    fake, client, factory = env
    to_planned(fake, client, factory, binding=30)
    client.post("/tasks/1/start", headers=HX)
    started = task_row(factory).started_at
    client.get("/tasks/1")
    assert task_row(factory).started_at == started and task_row(factory).status == "running"
    shift_start(factory, 31)
    r = client.get("/tasks/1/stage")
    assert task_row(factory).status == "checkpoint" and "נקודת עצירה" in r.text


def test_checkpoint_extend_once_then_stop_and_deep_retro(env):
    fake, client, factory = env
    to_planned(fake, client, factory, binding=30)
    client.post("/tasks/1/start", headers=HX)
    shift_start(factory, 31)
    client.get("/tasks/1")
    r = client.post("/tasks/1/checkpoint", headers=HX, data={
        "met_0": "on", "remaining": "חסר סיכום", "cause": "הפרעות", "choice": "extend", "extend_minutes": "10"})
    t = task_row(factory)
    assert t.status == "running" and t.extension_min == 10 and t.checkpoints[0].done_tests_met == [True]
    shift_start(factory, 11)
    r = client.get("/tasks/1/stage")
    assert 'value="extend"' not in r.text  # the extension is gone from the choices
    r = client.post("/tasks/1/checkpoint", headers=HX, data={"choice": "extend", "extend_minutes": "10"})
    assert "כבר השתמשת בהארכה" in r.text and task_row(factory).extension_min == 10
    client.post("/tasks/1/checkpoint", headers=HX, data={"choice": "stop", "cause": "נגמר הכוח"})
    t = task_row(factory)
    assert t.status == "retro" and t.outcome == "stopped" and t.blind_estimate_min == 30
    r = client.post("/tasks/1/retro", headers=HX, data={"cause": "הפרעות", "definition_gap": "", "lesson": "לחסום זמן"})
    t = task_row(factory)
    assert t.status == "closed" and t.retro.kind == "deep" and t.retro.lesson == "לחסום זמן"


def test_split_creates_children_that_start_their_own_interview(env):
    fake, client, factory = env
    to_planned(fake, client, factory, binding=30)
    client.post("/tasks/1/start", headers=HX)
    shift_start(factory, 31)
    client.get("/tasks/1")
    client.post("/tasks/1/checkpoint", headers=HX, data={"choice": "split", "children": "חלק א\n\nחלק ב\n"})
    s = factory()
    children = s.scalars(select(Task).where(Task.parent_id == 1).order_by(Task.id)).all()
    assert [c.opening_text for c in children] == ["חלק א", "חלק ב"]
    s.close()
    assert task_row(factory).outcome == "split"
    r = client.get(f"/tasks/{children[0].id}")
    assert "להתחיל את הראיון" in r.text
    fake.queue("judge", judged())
    fake.queue("ask", question("מה התוצר של חלק א?"))
    r = client.post(f"/tasks/{children[0].id}/retry", headers=HX)
    assert "מה התוצר של חלק א?" in r.text


def test_reduce_scope_keeps_listed_tests_and_continues(env):
    fake, client, factory = env
    to_planned(fake, client, factory, binding=30)
    client.post("/tasks/1/start", headers=HX)
    shift_start(factory, 31)
    client.get("/tasks/1")
    client.post("/tasks/1/checkpoint", headers=HX, data={"choice": "reduce", "reduce_tests": "המייל נשלח?", "reduce_minutes": "5"})
    t = task_row(factory)
    assert t.status == "running" and t.scope_reduced and t.done_tests == ["המייל נשלח?"] and t.extension_min == 5


def test_under_estimate_asks_too_simple_and_shortens_in_hindsight(env):
    fake, client, factory = env
    to_planned(fake, client, factory, blind=30, binding=60)
    client.post("/tasks/1/start", headers=HX)
    shift_start(factory, 19)
    r = client.post("/tasks/1/finish", headers=HX)
    assert "פשוטה מדי" in r.text
    r = client.post("/tasks/1/retro", headers=HX, data={"too_simple": "yes", "hindsight": "25", "cause": "", "definition_gap": "", "lesson": ""})
    assert "קצר מהזמן שנמדד" in r.text  # 25 is not below the measured 20
    client.post("/tasks/1/retro", headers=HX, data={"too_simple": "yes", "hindsight": "10", "cause": "", "definition_gap": "", "lesson": ""})
    t = task_row(factory)
    assert t.actual_min == 10 and t.shortened_in_hindsight and t.retro.too_simple is True


def test_history_and_spend_show_the_data(env):
    fake, client, factory = env
    to_planned(fake, client, factory)
    r = client.get("/history")
    assert "מייל למנהל" in r.text
    r = client.get("/spend")
    # judge (haiku) x2, ask (opus) x1, propose (opus) x1 at 1000 in / 200 out each.
    expected = 2 * (1000 * 0.1 + 200 * 0.5) / 1e6 + 2 * (1000 * 4 + 200 * 20) / 1e6
    assert f"${expected:.2f}" in r.text


def test_model_failure_shows_hebrew_error_and_retry(env):
    fake, client, factory = env
    fake.queue("judge", CallFailed("overloaded"))
    r = client.post("/tasks", data={"opening": "לסדר את המחסן"})
    assert r.status_code == 400 and "לא הצלחתי להגיע למודל" in r.text and "לנסות שוב" in r.text
    r = client.get("/tasks/1")  # coming back later: the task waits for its first step
    assert "להתחיל את הראיון" in r.text
    fake.queue("judge", judged())
    fake.queue("ask", question("מה התוצר?"))
    r = client.post("/tasks/1/retry", headers=HX)
    assert "מה התוצר?" in r.text


def test_unknown_task_is_404(env):
    fake, client, factory = env
    assert client.get("/tasks/999").status_code == 404
    assert client.post("/tasks/999/answer", data={"answer": "x"}).status_code == 404


def test_double_submit_does_not_answer_the_next_question(env):
    fake, client, factory = env
    fake.queue("judge", judged(), judged(deliverable="מייל"))
    fake.queue("ask", question("שאלה 1?"), question("שאלה 2?"))
    client.post("/tasks", data={"opening": "מייל"})
    client.post("/tasks/1/answer", data={"answer": "מייל", "round": "1"})
    r = client.post("/tasks/1/answer", data={"answer": "מייל", "round": "1"})  # the same form again
    assert "כבר נענתה" in r.text
    s = factory()
    assert [t.answer for t in s.get(Task, 1).turns] == ["מייל", None]
    s.close()
