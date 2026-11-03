"""Three whole journeys through the web app, one after another in one database,
with a scripted model. Each covers a different route through the process, and
the later tasks check what the earlier ones left behind (history, lessons).

A. smooth: interview -> edited breakdown -> estimate -> on time -> short retro
B. gap:    required clarification -> extension -> over time -> deep retro with a lesson
C. big:    the lesson reaches its interview -> checkpoint -> split -> child starts over
"""

from tests.helpers import GOOD_CARD, breakdown, judged, proposal, question
from tests.integration.test_web_flow import HX, env, review_breakdown, shift_start, task_row  # noqa: F401  (env is a fixture)


def define(fake, client, opening, type_key):
    """Interview with one clarifying round, ending in a ready card."""
    fake.queue("judge", judged(type_key=type_key, deliverable=GOOD_CARD["deliverable"]))
    fake.queue("ask", question("מה המבחן?"))
    client.post("/tasks", data={"opening": opening})
    fake.queue("judge", judged(**dict(GOOD_CARD, type_key=type_key)))


def test_three_tasks_through_the_whole_process(env):
    fake, client, factory = env

    # ---- A: smooth path -------------------------------------------------------
    define(fake, client, "לכתוב מייל למנהל", "write")
    r = client.post("/tasks/1/answer", data={"answer": "הכול"}, headers=HX)
    t = task_row(factory)
    assert t.status == "estimate" and t.breakdown is None
    assert "להציע פירוק" in r.text and 'name="minutes"' not in r.text  # no time before the breakdown

    fake.queue("breakdown", breakdown(3))  # חלק 1..3
    client.post("/tasks/1/breakdown/propose", headers=HX)
    # the person drops part 2, renames part 3 and adds a new one
    client.post("/tasks/1/breakdown", data={"title": ["חלק 1", "חלק 2", "חלק 3"], "action": "remove:1"}, headers=HX)
    client.post("/tasks/1/breakdown", data={"title": ["חלק 1", "ניסוח סופי"], "action": "add"}, headers=HX)
    client.post("/tasks/1/breakdown", data={"title": ["חלק 1", "ניסוח סופי", "שליחה"], "action": "confirm"}, headers=HX)
    t = task_row(factory)
    assert t.breakdown == ["חלק 1", "ניסוח סופי", "שליחה"] and t.breakdown_confirmed

    fake.queue("propose", proposal(45))
    r = client.post("/tasks/1/blind", data={"minutes": "40"}, headers=HX)
    prompt = fake.calls[-1]["user"]
    assert "ניסוח סופי" in prompt and "שליחה" in prompt and "חלק 2" not in prompt  # the model got the edited list
    t = task_row(factory)
    assert (t.blind_estimate_min, t.model_estimate_min, t.needed_clarification) == (40, 45, False)
    assert "ההערכה המחייבת" in r.text and "פער של פי 2" not in r.text

    client.post("/tasks/1/binding", data={"minutes": "45"}, headers=HX)
    client.post("/tasks/1/start", headers=HX)
    shift_start(factory, 39)  # measured time rounds up
    r = client.post("/tasks/1/finish", headers=HX)
    assert task_row(factory).status == "retro"  # waits for the breakdown review
    review_breakdown(client, factory)
    t = task_row(factory)
    assert t.status == "closed" and t.outcome == "completed" and t.retro.kind == "short" and t.actual_min == 40
    assert t.breakdown_review["items"][0]["verdict"] == "done" and t.breakdown_review["missing"] == []

    # ---- B: gap, clarification, extension, over time, deep retro ---------------
    define(fake, client, "לתקן באג בייצוא", "build")
    client.post("/tasks/2/answer", data={"answer": "הכול"}, headers=HX)
    fake.queue("breakdown", breakdown(2))
    client.post("/tasks/2/breakdown/propose", headers=HX)
    client.post("/tasks/2/breakdown", data={"title": ["חלק 1", "חלק 2"], "action": "confirm"}, headers=HX)
    fake.queue("propose", proposal(90))  # 90 vs 30: 3x
    r = client.post("/tasks/2/blind", data={"minutes": "30"}, headers=HX)
    assert task_row(factory, 2).needed_clarification and "פער של פי 2" in r.text
    r = client.post("/tasks/2/binding", data={"minutes": "30"}, headers=HX)
    assert "לא מתאימה" in r.text and task_row(factory, 2).status == "estimate"  # cannot skip the round
    fake.queue("propose", proposal(50))
    client.post("/tasks/2/clarify", data={"clarification": "רק הייצוא, בלי הייבוא"}, headers=HX)
    t = task_row(factory, 2)
    assert t.model_estimate_min == 50 and t.blind_estimate_min == 30  # blind never changes
    assert t.breakdown == ["חלק 1", "חלק 2"]  # the confirmed breakdown is untouched by the round
    client.post("/tasks/2/binding", data={"minutes": "60"}, headers=HX)
    client.post("/tasks/2/start", headers=HX)
    shift_start(factory, 61, task_id=2)
    client.get("/tasks/2")
    assert task_row(factory, 2).status == "checkpoint"
    client.post("/tasks/2/checkpoint", headers=HX, data={
        "met_0": "on", "remaining": "בדיקות", "cause": "מקרה קצה", "choice": "extend", "extend_minutes": "15"})
    assert task_row(factory, 2).status == "running"
    shift_start(factory, 9, task_id=2)  # 70 minutes in total, 75 allowed
    client.post("/tasks/2/finish", headers=HX)
    t = task_row(factory, 2)
    assert t.status == "retro"  # over the binding estimate: a retrospective is required
    review_breakdown(client, factory, task_id=2, verdict="unneeded", missing="לבדוק קובץ ריק")
    t = task_row(factory, 2)
    assert t.status == "retro" and t.breakdown_review["missing"] == ["לבדוק קובץ ריק"]
    client.post("/tasks/2/retro", headers=HX, data={
        "cause": "מקרה קצה", "definition_gap": "לא הוגדר איך נראה קובץ ריק", "lesson": "לבדוק קבצים ריקים מראש"})
    t = task_row(factory, 2)
    assert t.status == "closed" and t.outcome == "completed" and t.retro.kind == "deep"
    assert t.actual_min >= 70

    # ---- C: the lesson of B reaches the next 'build' task; split at the checkpoint ----
    fake.queue("judge", judged(type_key="build", deliverable="מערכת חדשה"))
    fake.queue("ask", question("מה התוצר?"))
    client.post("/tasks", data={"opening": "לבנות מערכת דוחות"})
    assert "לבדוק קבצים ריקים מראש" in fake.calls[-1]["user"]  # asked with the lesson in front of it
    fake.queue("judge", judged(**dict(GOOD_CARD, type_key="build")))
    client.post("/tasks/3/answer", data={"answer": "הכול"}, headers=HX)
    fake.queue("breakdown", breakdown(5))
    client.post("/tasks/3/breakdown/propose", headers=HX)
    client.post("/tasks/3/breakdown", data={"title": breakdown(5).subtasks, "action": "confirm"}, headers=HX)
    fake.queue("propose", proposal(60))
    client.post("/tasks/3/blind", data={"minutes": "60"}, headers=HX)
    client.post("/tasks/3/binding", data={"minutes": "60"}, headers=HX)
    client.post("/tasks/3/start", headers=HX)
    shift_start(factory, 61, task_id=3)
    client.get("/tasks/3")
    client.post("/tasks/3/checkpoint", headers=HX, data={"choice": "split", "children": "דוח ראשון\nדוח שני"})
    parent = task_row(factory, 3)
    assert parent.outcome == "split"
    child = task_row(factory, 4)
    assert child.parent_id == 3 and child.opening_text == "דוח ראשון" and child.status == "interview"

    # the child goes through the same new order: card -> breakdown -> estimate
    fake.queue("judge", judged(**dict(GOOD_CARD, type_key="build")))
    client.post("/tasks/4/retry", headers=HX)
    child = task_row(factory, 4)
    assert child.status == "estimate" and child.breakdown is None

    # ---- the numbers over all three ----------------------------------------------
    assert client.get("/history").status_code == 200
    page = client.get("/history").text
    assert "מייל למנהל" in page
    spend = client.get("/spend")
    assert spend.status_code == 200 and "פירוק לתת־משימות" in spend.text  # the new call is itemised
