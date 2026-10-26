"""Data from finished tasks flows back: calibration and retro lessons."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from task_compass.config import Settings
from task_compass.llm.fake import FakeClient
from task_compass.models import Category, Retro, Task
from task_compass.wiring import build_services
from tests.helpers import GOOD_CARD, judged, proposal, question


def finished(session, type_key, blind, actual, outcome="completed", days_ago=1, lesson=None):
    cat = session.scalar(select(Category).where(Category.key == type_key))
    t = Task(opening_text=f"{type_key} {blind}->{actual}", category_id=cat.id, status="closed", outcome=outcome,
             blind_estimate_min=blind, binding_estimate_min=blind, actual_min=actual,
             finished_at=datetime.now(timezone.utc) - timedelta(days=days_ago))
    session.add(t)
    session.flush()
    if lesson:
        session.add(Retro(task_id=t.id, kind="deep", direction="over", lesson=lesson))
    session.commit()
    return t


def ready_task(services, fake, type_key="write"):
    fake.queue("judge", judged(**dict(GOOD_CARD, type_key=type_key)))
    return services.interview.start("משימה")


def services_with(session_factory):
    fake = FakeClient()
    return fake, build_services(fake, session_factory, Settings(anthropic_api_key="", monthly_cost_cap_usd=10))


def test_type_factor_global_fallback_and_none(session_factory, session):
    fake, svc = services_with(session_factory)

    task_id = ready_task(svc, fake)
    fake.queue("propose", proposal(30))
    svc.estimate.submit_blind(task_id, "30")
    t = session.get(Task, task_id)
    assert (t.calibration_source, t.calibration_factor, t.corrected_estimate_min) == ("none", 1.0, 30)

    for blind, actual in ((10, 20), (10, 30), (10, 20)):
        finished(session, "build", blind, actual)
    task_id = ready_task(svc, fake)
    fake.queue("propose", proposal(30))
    svc.estimate.submit_blind(task_id, "30")
    session.expire_all()
    t = session.get(Task, task_id)
    assert (t.calibration_source, t.calibration_factor, t.corrected_estimate_min) == ("global", 2.0, 60)

    for blind, actual in ((10, 12), (10, 15), (10, 15)):
        finished(session, "write", blind, actual, days_ago=0)
    task_id = ready_task(svc, fake)
    fake.queue("propose", proposal(30))
    svc.estimate.submit_blind(task_id, "30")
    session.expire_all()
    t = session.get(Task, task_id)
    assert (t.calibration_source, t.calibration_factor, t.corrected_estimate_min) == ("type", 1.5, 45)


def test_stopped_and_split_tasks_do_not_calibrate(session_factory, session):
    fake, svc = services_with(session_factory)
    for outcome in ("stopped", "split", "stopped"):
        finished(session, "write", 10, 50, outcome=outcome)
    task_id = ready_task(svc, fake)
    fake.queue("propose", proposal(30))
    svc.estimate.submit_blind(task_id, "30")
    assert session.get(Task, task_id).calibration_source == "none"


def test_hindsight_shortened_time_is_what_calibrates(session_factory, session):
    fake, svc = services_with(session_factory)
    for _ in range(3):
        task_id = ready_task(svc, fake)
        fake.queue("propose", proposal(30))
        svc.estimate.submit_blind(task_id, "30")
        svc.estimate.set_binding(task_id, "60")
        svc.execution.start(task_id)
        t = session.get(Task, task_id)
        t.started_at -= timedelta(minutes=30)
        session.commit()
        svc.execution.finish(task_id)  # 30 of 60: under, asks "too simple?"
        svc.retro.submit(task_id, cause="", definition_gap="", lesson="", too_simple=True, hindsight_min="15")
    session.expire_all()
    rows = session.scalars(select(Task).where(Task.outcome == "completed")).all()
    assert all(r.actual_min == 15 and r.shortened_in_hindsight for r in rows)
    task_id = ready_task(svc, fake)
    fake.queue("propose", proposal(30))
    svc.estimate.submit_blind(task_id, "40")
    t = session.get(Task, task_id)
    assert (t.calibration_source, t.calibration_factor, t.corrected_estimate_min) == ("type", 0.5, 20)


def test_retro_lessons_reach_the_next_interview_of_the_same_type(session_factory, session):
    fake, svc = services_with(session_factory)
    finished(session, "write", 10, 20, lesson="מיילים למנהל דורשים טיוטה ובדיקה")
    finished(session, "build", 10, 20, lesson="לקח של בנייה")
    fake.queue("judge", judged(type_key="write"))
    fake.queue("ask", question())
    svc.interview.start("לכתוב מייל")
    ask_prompt = fake.calls[-1]["user"]
    assert "מיילים למנהל דורשים טיוטה ובדיקה" in ask_prompt
    assert "לקח של בנייה" not in ask_prompt
