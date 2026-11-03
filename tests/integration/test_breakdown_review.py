"""After a task ends the person reviews the breakdown; the numbers are stored for later scoring."""

import pytest

from task_compass.domain.breakdown_review import build_review, quality
from tests.integration.test_web_flow import HX, env, review_breakdown, shift_start, task_row, to_planned  # noqa: F401


def finished_task(env, minutes=39):
    fake, client, factory = env
    to_planned(fake, client, factory, binding=40)
    client.post("/tasks/1/start", headers=HX)
    shift_start(factory, minutes)
    return client.post("/tasks/1/finish", headers=HX)


def test_quality_numbers():
    review = build_review(["א", "ב", "ג", "ד"], ["done", "done", "weak", "unneeded"], "ה\n\n ו ")
    q = quality(review)
    assert (q.planned, q.done, q.weak, q.unneeded, q.missing) == (4, 2, 1, 1, 2)
    assert q.needed == 5 and q.relevance == 0.75 and q.coverage == pytest.approx(3 / 5) and not q.clean
    assert quality(build_review(["א"], ["done"], "")).clean


def test_review_needs_a_verdict_for_every_subtask():
    with pytest.raises(ValueError):
        build_review(["א", "ב"], ["done"], "")
    with pytest.raises(ValueError):
        build_review(["א"], ["great"], "")


def test_the_retro_waits_for_the_review(env):
    r = finished_task(env)
    fake, client, factory = env
    assert task_row(factory).status == "retro" and "חלק 1" in r.text and 'name="verdict_0"' in r.text
    r = client.post("/tasks/1/retro", headers=HX, data={"cause": "", "definition_gap": "", "lesson": ""})
    assert "לא מתאימה לשלב" in r.text and task_row(factory).status == "retro"


def test_incomplete_review_is_refused_and_keeps_the_screen(env):
    finished_task(env)
    fake, client, factory = env
    r = client.post("/tasks/1/review", data={"verdict_0": "done", "missing": "משהו"}, headers=HX)  # verdict_1 missing
    assert "לסמן לכל תת־משימה" in r.text and task_row(factory).breakdown_review is None


def test_review_is_saved_with_missing_subtasks_and_shown_in_history(env):
    finished_task(env)
    fake, client, factory = env
    review_breakdown(client, factory, missing="לשלוח תזכורת\nלעדכן את המנהל")
    t = task_row(factory)
    assert t.status == "closed"
    assert [i["verdict"] for i in t.breakdown_review["items"]] == ["done", "done"]
    assert t.breakdown_review["missing"] == ["לשלוח תזכורת", "לעדכן את המנהל"]
    assert t.breakdown == ["חלק 1", "חלק 2"]  # the original plan is kept untouched
    history = client.get("/history").text
    assert "2/2" in history and "+2" in history
    assert "הייתה חסרה" in client.get("/tasks/1").text
    # reviewing twice is not possible
    review_breakdown(client, factory, verdict="unneeded")
    assert [i["verdict"] for i in task_row(factory).breakdown_review["items"]] == ["done", "done"]
