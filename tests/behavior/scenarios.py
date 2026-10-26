"""The layer 2 test tasks (decisions doc, "Readiness criteria").

Each scenario has an opening text, a simulated user, and checks over the
trace of the interview. scripts/run_behavior_live.py runs them against the
real model 3 times each; tests/behavior/test_interview_flow.py covers the same
cases with scripted model answers.

Tasks 7 to 10 are drafts and still need Daniel's approval.
"""

from dataclasses import dataclass, field
from typing import Callable

from task_compass.llm.gateway import count_questions

# A trace step is the state shown to the user after the opening text and after
# each answer: {"round" (the open question's round, or the number of answered
# rounds once the interview ended), "field", "question", "note", "status",
# "verdicts", "type_key"}
Trace = list[dict]


@dataclass
class Scenario:
    id: int
    name: str
    opening: str
    # answer(round_no, field_asked) -> the simulated user's reply
    answer: Callable[[int, str], str]
    checks: list[Callable[[Trace], str | None]] = field(default_factory=list)
    max_answers: int = 12  # how many times the simulated user answers
    change_type_at: tuple[int, str] | None = None  # (round, new type key)
    draft: bool = False


def by_field(answers: dict[str, str], default: str = "לא בטוח") -> Callable[[int, str], str]:
    return lambda _round, field_name: answers.get(field_name, default)


# --- checks that apply to every scenario --------------------------------------

def one_question_per_turn(trace: Trace) -> str | None:
    for step in trace:
        if step["question"] and count_questions(step["question"]) > 1:
            return f"round {step['round']}: more than one question"
    return None


def asks_only_failing_fields(trace: Trace) -> str | None:
    for step in trace:
        if step["field"] and step["verdicts"].get(step["field"], {}).get("status") == "pass":
            return f"round {step['round']}: asked about {step['field']}, which already passed"
    return None


def ready_only_when_all_pass(trace: Trace) -> str | None:
    for step in trace:
        if step["status"] == "estimate" and any(v["status"] != "pass" for v in step["verdicts"].values()):
            return "reached estimation with a failing field"
    return None


COMMON_CHECKS = [one_question_per_turn, asks_only_failing_fields, ready_only_when_all_pass]


# --- check builders -----------------------------------------------------------

def verdict_after(round_no: int, field_name: str, status: str):
    def check(trace: Trace) -> str | None:
        step = next((s for s in trace if s["round"] == round_no), None)
        got = step and step["verdicts"].get(field_name, {}).get("status")
        return None if got == status else f"after round {round_no}: {field_name} is {got}, expected {status}"
    return check


def asks_about(round_no: int, field_name: str):
    def check(trace: Trace) -> str | None:
        step = next((s for s in trace if s["round"] == round_no), None)
        got = step and step["field"]
        return None if got == field_name else f"round {round_no}: asked about {got}, expected {field_name}"
    return check


def suggested_type(type_key: str):
    def check(trace: Trace) -> str | None:
        got = trace[0]["type_key"] if trace else None
        return None if got == type_key else f"suggested type {got}, expected {type_key}"
    return check


def ends_with(status: str, within_rounds: int | None = None):
    def check(trace: Trace) -> str | None:
        last = trace[-1] if trace else {}
        if last.get("status") != status:
            return f"ended as {last.get('status')}, expected {status}"
        if within_rounds is not None and last["round"] > within_rounds:
            return f"took {last['round']} rounds, expected at most {within_rounds}"
        return None
    return check


def never_ready(trace: Trace) -> str | None:
    return "reached estimation" if any(s["status"] == "estimate" for s in trace) else None


def note_after_enough(trace: Trace) -> str | None:
    return None if any(s["note"] for s in trace) else "no missing-fields note after 'enough'"


SCENARIOS = [
    Scenario(1, "activity is not a deliverable", "לסדר את המחסן",
             answer=lambda r, f: "לעבוד על המחסן" if r == 1 else "לא יודע",
             checks=[asks_about(1, "deliverable"), verdict_after(2, "deliverable", "fail"),
                     asks_about(2, "deliverable")], max_answers=1),
    Scenario(2, "vague done test", "לטפל בדוח",
             answer=by_field({"deliverable": "דוח רבעוני בקובץ PDF", "done_tests": "הדוח טוב"}),
             checks=[lambda t: verdict_after(t[-1]["round"], "done_tests", "fail")(t),
                     lambda t: asks_about(t[-1]["round"], "done_tests")(t)], max_answers=2),
    Scenario(3, "enough does not close", "ללמוד SQL",
             answer=lambda r, f: "פתרון 3 תרגילי JOIN בלי עזרה" if r == 1 else "מספיק",
             checks=[note_after_enough, never_ready], max_answers=2),
    Scenario(4, "good answers reach estimation", "לכתוב מייל למנהל",
             answer=by_field({
                 "deliverable": "מייל למנהל עם עדכון סטטוס על פרויקט הגיבוי, שנשלח",
                 "done_tests": "המייל נשלח למנהל? המייל כולל תאריך סיום משוער?",
                 "boundaries": "לא כולל קביעת פגישה ולא כולל מצגת",
                 "first_step": "לפתוח טיוטה חדשה בג'ימייל עם הנושא 'סטטוס גיבוי'",
             }),
             checks=[suggested_type("write"), ends_with("estimate", within_rounds=6)], max_answers=6),
    Scenario(5, "twelve vague rounds", "לבנות מערכת CRM",
             answer=lambda r, f: "משהו שיעבוד טוב, נראה בהמשך",
             checks=[ends_with("stuck"), never_ready]),
    Scenario(6, "decide type needs a written decision", "להחליט איזה מחשב נייד לקנות",
             answer=by_field({"deliverable": "פתק עם המחשב שבחרתי", "done_tests": "חשבתי על זה"}),
             checks=[suggested_type("decide"),
                     lambda t: verdict_after(t[-1]["round"], "done_tests", "fail")(t)], max_answers=2),
    # Drafts, waiting for Daniel's approval.
    Scenario(7, "errands", "סידורים בעיר",
             answer=by_field({
                 "deliverable": "שלושה סידורים שבוצעו: חבילה מהדואר, מרשם מקופת חולים, חידוש רישיון",
                 "done_tests": "החבילה נאספה? התרופה נאספה? הרישיון חודש?",
                 "boundaries": "לא כולל קניות בסופר",
                 "first_step": "להדפיס את טופס חידוש הרישיון",
             }),
             checks=[suggested_type("errands"), ends_with("estimate", within_rounds=6)], max_answers=6, draft=True),
    Scenario(8, "bug fix", "לתקן את הבאג בייצוא",
             answer=by_field({
                 "deliverable": "ייצוא CSV שעובד גם עם שמות בעברית",
                 "done_tests": "ייצוא של רשימה עם שם בעברית נפתח באקסל בלי ג'יבריש?",
                 "boundaries": "לא כולל ייצוא ל-PDF",
                 "first_step": "לייצא את הרשימה הבעייתית ולשמור את הקובץ כדוגמה",
             }),
             checks=[suggested_type("fix"), ends_with("estimate", within_rounds=6)], max_answers=6, draft=True),
    Scenario(9, "type changed midway", "לכתוב סקריפט גיבוי",
             answer=by_field({"deliverable": "סקריפט גיבוי שרץ כל לילה", "done_tests": "הסקריפט רץ?"}),
             change_type_at=(2, "fix"),
             checks=[lambda t: None if t[-1]["type_key"] == "fix" else "type was not changed"],
             max_answers=2, draft=True),
    Scenario(10, "partial answer that improves", "להכין מצגת",
             answer=lambda r, f: {1: "מצגת", 2: "מצגת של 10 שקפים על תוצאות הרבעון, בקובץ PPTX בתיקייה המשותפת"}.get(r, "לא יודע"),
             checks=[verdict_after(2, "deliverable", "fail"), verdict_after(3, "deliverable", "pass")],
             max_answers=2, draft=True),
]
