"""Pausing a running task: the clock and focus mode stop, resuming gives the time back."""

from datetime import timedelta

import pytest

from task_compass.config import Settings
from task_compass.llm.fake import FakeClient
from task_compass.models import Task
from task_compass.web import create_app
from task_compass.wiring import build_services
from tests.integration.test_web_flow import HX, to_planned


@pytest.fixture
def env(session_factory):
    fake = FakeClient()
    services = build_services(fake, session_factory, Settings(anthropic_api_key="", monthly_cost_cap_usd=10, debug_log_calls=False))
    client = create_app(services).test_client()
    to_planned(fake, client, session_factory)
    client.post("/tasks/1/start", headers=HX)
    return client, session_factory


def edit(factory, **minutes_back):
    """Move started_at and/or paused_at into the past."""
    with factory() as s:
        t = s.get(Task, 1)
        for field, minutes in minutes_back.items():
            setattr(t, field, getattr(t, field) - timedelta(minutes=minutes))
        s.commit()


def row(factory) -> Task:
    with factory() as s:
        return s.get(Task, 1)


def test_pause_stops_the_clock_and_focus(env):
    client, factory = env
    assert client.get("/api/focus").get_json()["active"] is True
    client.post("/tasks/1/pause", headers=HX)
    assert row(factory).status == "paused"
    assert client.get("/api/focus").get_json()["active"] is False
    page = client.get("/tasks/1").text
    assert "להמשיך" in page and "data-deadline" not in page  # a frozen time, no live countdown


def test_a_paused_task_never_reaches_the_checkpoint(env):
    client, factory = env
    client.post("/tasks/1/pause", headers=HX)
    edit(factory, started_at=3 * 24 * 60, paused_at=3 * 24 * 60)
    client.get("/tasks/1")
    assert row(factory).status == "paused"


def test_resume_gives_the_paused_time_back(env):
    client, factory = env
    client.post("/tasks/1/pause", headers=HX)
    edit(factory, paused_at=60)  # it has been paused for an hour
    before = row(factory)
    client.post("/tasks/1/resume", headers=HX)
    after = row(factory)
    assert after.status == "running" and after.paused_at is None
    assert after.started_at - before.started_at >= timedelta(minutes=59)  # the pause was added to the start
    assert client.get("/api/focus").get_json()["active"] is True


def test_paused_time_is_not_counted_when_finishing_from_pause(env):
    client, factory = env
    edit(factory, started_at=10)
    client.post("/tasks/1/pause", headers=HX)
    edit(factory, paused_at=300)  # paused for 5 hours
    client.post("/tasks/1/finish", headers=HX)
    t = row(factory)
    assert t.status in ("retro", "closed") and t.actual_min <= 11


def test_only_a_running_task_can_pause_and_only_a_paused_one_resume(env):
    client, factory = env
    assert "הפעולה הזאת לא מתאימה" in client.post("/tasks/1/resume", headers=HX).text
    client.post("/tasks/1/pause", headers=HX)
    assert "הפעולה הזאת לא מתאימה" in client.post("/tasks/1/pause", headers=HX).text
