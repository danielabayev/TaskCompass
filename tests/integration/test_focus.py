"""Focus mode: the API the browser extension uses, with a scripted model."""

import pytest

from datetime import timedelta

from task_compass.config import Settings
from task_compass.llm.fake import FakeClient
from task_compass.llm.gateway import CallFailed
from task_compass.models import Task
from task_compass.web import create_app
from task_compass.wiring import build_services
from tests.helpers import site_verdicts
from tests.integration.test_web_flow import HX, to_planned

HISTORY = {"sites": [{"domain": "www.docs.python.org", "title": "Docs"},
                     {"domain": "youtube.com", "title": "Funny cats"},
                     {"domain": "127.0.0.1", "title": "Task Compass"}]}


@pytest.fixture
def env(session_factory):
    fake = FakeClient()
    services = build_services(fake, session_factory, Settings(anthropic_api_key="", monthly_cost_cap_usd=10, debug_log_calls=False))
    return fake, create_app(services).test_client(), session_factory


def post(client, path, **body):
    return client.post(path, json=body).get_json()


def running(env):
    fake, client, factory = env
    to_planned(fake, client, factory)
    client.post("/tasks/1/start", headers=HX)
    return fake, client


def test_no_running_task_blocks_nothing(env):
    fake, client, factory = env
    assert client.get("/api/focus").get_json()["active"] is False
    assert post(client, "/api/focus/check", domain="youtube.com", title="x") == {"active": False, "blocked": False, "reason": ""}
    assert fake.calls == [] or all(c["purpose"] != "sites" for c in fake.calls)


def test_planned_task_is_not_focus(env):
    fake, client, factory = env
    to_planned(fake, client, factory)
    assert client.get("/api/focus").get_json()["active"] is False


def test_history_is_judged_and_unhelpful_sites_are_blocked(env):
    fake, client = running(env)
    fake.queue("sites", site_verdicts(**{"docs.python.org": True, "youtube.com": False}))
    status = post(client, "/api/focus/history", **HISTORY)
    assert status["active"] and status["task_id"] == 1
    assert [s["domain"] for s in status["blocked"]] == ["youtube.com"]
    sent = fake.calls[-1]["user"]
    assert "docs.python.org" in sent and "youtube.com" in sent
    assert "127.0.0.1" not in sent and "www." not in sent  # the tool itself is skipped, only domains are sent


def test_new_site_is_checked_once_then_remembered(env):
    fake, client = running(env)
    fake.queue("sites", site_verdicts(**{"reddit.com": False}))
    first = post(client, "/api/focus/check", domain="reddit.com", title="front page")
    assert first["blocked"] is True and first["reason"]
    calls = len(fake.calls)
    assert post(client, "/api/focus/check", domain="www.reddit.com", title="again")["blocked"] is True
    assert len(fake.calls) == calls  # no second model call


def test_useful_site_is_not_blocked(env):
    fake, client = running(env)
    fake.queue("sites", site_verdicts(**{"stackoverflow.com": True}))
    assert post(client, "/api/focus/check", domain="stackoverflow.com", title="q")["blocked"] is False
    assert client.get("/api/focus").get_json()["blocked"] == []


def test_allow_overrides_the_block(env):
    fake, client = running(env)
    fake.queue("sites", site_verdicts(**{"reddit.com": False}))
    post(client, "/api/focus/check", domain="reddit.com", title="x")
    status = post(client, "/api/focus/allow", domain="reddit.com")
    assert status["blocked"] == []
    assert post(client, "/api/focus/check", domain="reddit.com", title="x")["blocked"] is False


def test_model_failure_blocks_nothing(env):
    fake, client = running(env)
    fake.queue("sites", CallFailed("down"), CallFailed("down"))
    r = post(client, "/api/focus/check", domain="reddit.com", title="x")
    assert r["blocked"] is False and r["error"]
    assert client.get("/api/focus").get_json()["blocked"] == []


def test_finishing_the_task_lifts_every_block(env):
    fake, client = running(env)
    fake.queue("sites", site_verdicts(**{"reddit.com": False}))
    post(client, "/api/focus/check", domain="reddit.com", title="x")
    client.post("/tasks/1/finish", headers=HX)
    assert client.get("/api/focus").get_json() == {"active": False, "task_id": None, "task_title": None, "blocked": []}
    assert post(client, "/api/focus/check", domain="reddit.com", title="x")["blocked"] is False


def test_tool_itself_is_never_judged(env):
    fake, client = running(env)
    r = post(client, "/api/focus/check", domain="localhost", title="Task Compass")
    assert r["blocked"] is False
    assert all(c["purpose"] != "sites" for c in fake.calls)


def test_focus_stays_on_when_time_runs_out_until_the_task_is_finished(env):
    fake, client = running(env)
    fake.queue("sites", site_verdicts(**{"reddit.com": False}))
    post(client, "/api/focus/check", domain="reddit.com", title="x")
    s = client.application.extensions["task_compass"].session_factory()
    t = s.get(Task, 1)
    t.started_at = t.started_at - timedelta(days=1)
    s.commit()
    s.close()
    client.get("/tasks/1")  # opening the page moves the overdue task to the checkpoint
    assert task_status(env) == "checkpoint"
    assert [b["domain"] for b in client.get("/api/focus").get_json()["blocked"]] == ["reddit.com"]
    client.post("/tasks/1/finish", headers=HX)
    assert client.get("/api/focus").get_json()["active"] is False


def task_status(env):
    s = env[2]()
    status = s.get(Task, 1).status
    s.close()
    return status
