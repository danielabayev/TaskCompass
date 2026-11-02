"""Managing tasks: delete, nest under another, group."""

import pytest
from sqlalchemy import select

from task_compass.config import Settings
from task_compass.llm.fake import FakeClient
from task_compass.models import InterviewTurn, LlmCall, SiteVerdict, Task, TaskGroup
from task_compass.web import create_app
from task_compass.wiring import build_services
from tests.integration.test_web_flow import HX, to_planned


@pytest.fixture
def env(session_factory):
    fake = FakeClient()
    services = build_services(fake, session_factory, Settings(anthropic_api_key="", monthly_cost_cap_usd=10, debug_log_calls=False))
    return fake, create_app(services).test_client(), session_factory, services.manage


def add_tasks(factory, n, **fields):
    with factory() as s:
        for i in range(n):
            s.add(Task(opening_text=f"משימה {i + 1}", **fields))
        s.commit()


def get(factory, task_id):
    with factory() as s:
        return s.get(Task, task_id)


def test_manage_page_renders(env):
    fake, client, factory, manage = env
    add_tasks(factory, 2)
    r = client.get("/manage")
    assert r.status_code == 200 and "משימה 1" in r.text and 'dir="rtl"' in r.text


def test_delete_removes_the_task_and_everything_attached(env):
    fake, client, factory, manage = env
    to_planned(fake, client, factory)
    with factory() as s:
        s.add(SiteVerdict(task_id=1, domain="x.com", useful=False))
        s.commit()
    r = client.post("/manage/tasks/1/delete")
    assert r.status_code == 302
    with factory() as s:
        assert s.get(Task, 1) is None
        assert s.scalars(select(InterviewTurn)).all() == [] and s.scalars(select(SiteVerdict)).all() == []
        calls = s.scalars(select(LlmCall)).all()
        assert calls and all(c.task_id is None for c in calls)  # spend history survives


def test_deleting_a_parent_lifts_its_children(env):
    fake, client, factory, manage = env
    add_tasks(factory, 3)
    manage.set_parent(2, 1)
    manage.set_parent(3, 2)
    manage.delete_task(2)
    assert get(factory, 3).parent_id == 1
    manage.delete_task(1)
    assert get(factory, 3).parent_id is None


def test_nesting_inherits_group_and_group_moves_the_subtree(env):
    fake, client, factory, manage = env
    add_tasks(factory, 3)
    g = manage.create_group("עבודה")
    manage.set_group(1, g)
    manage.set_parent(2, 1)
    manage.set_parent(3, 2)
    assert [get(factory, i).group_id for i in (1, 2, 3)] == [g, g, g]
    h = manage.create_group("בית")
    manage.set_group(2, h)  # leaves its parent's group, so it becomes top-level there
    assert get(factory, 2).parent_id is None
    assert [get(factory, i).group_id for i in (2, 3)] == [h, h] and get(factory, 3).parent_id == 2


def test_cycles_and_self_parent_are_refused(env):
    fake, client, factory, manage = env
    add_tasks(factory, 2)
    manage.set_parent(2, 1)
    assert client.post("/manage/tasks/1/move", data={"parent_id": "2"}).status_code == 400
    assert client.post("/manage/tasks/1/move", data={"parent_id": "1"}).status_code == 400
    assert get(factory, 1).parent_id is None


def test_move_form_sets_group_then_parent(env):
    fake, client, factory, manage = env
    add_tasks(factory, 2)
    gid = manage.create_group("עבודה")
    client.post("/manage/tasks/1/move", data={"group_id": str(gid)})
    assert get(factory, 1).group_id == gid
    client.post("/manage/tasks/2/move", data={"parent_id": "1"})
    assert get(factory, 2).parent_id == 1 and get(factory, 2).group_id == gid
    client.post("/manage/tasks/2/move", data={"group_id": ""})
    assert get(factory, 2).parent_id is None and get(factory, 2).group_id is None


def test_groups_can_be_renamed_and_deleted_without_losing_tasks(env):
    fake, client, factory, manage = env
    add_tasks(factory, 1)
    client.post("/manage/groups", data={"name": "  עבודה  "})
    with factory() as s:
        assert s.scalars(select(TaskGroup.name)).all() == ["עבודה"]
    client.post("/manage/groups/1/rename", data={"name": "בית"})
    client.post("/manage/tasks/1/move", data={"group_id": "1"})
    client.post("/manage/groups/1/delete")
    with factory() as s:
        assert s.scalars(select(TaskGroup)).all() == []
    assert get(factory, 1).group_id is None
    assert client.post("/manage/groups", data={"name": "  "}).status_code == 400
