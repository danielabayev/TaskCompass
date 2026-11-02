"""Builders for scripted model answers used by the tests."""

from task_compass.llm.gateway import Gateway
from task_compass.llm.fake import FakeClient
from task_compass.llm.schemas import Breakdown, FieldVerdict, JudgeResult, Proposal, Question

OK = FieldVerdict(status="pass", reason="")


def bad(reason: str = "לא מספיק מוחשי") -> FieldVerdict:
    return FieldVerdict(status="fail", reason=reason)


def judged(type_key="write", deliverable=None, done_tests=(), boundaries=(), first_step=None, **verdicts) -> JudgeResult:
    """A judge answer. Fields with a value default to a pass verdict unless overridden,
    e.g. judged(deliverable="x", deliverable_verdict=bad())."""
    values = {"deliverable": deliverable, "done_tests": list(done_tests),
              "boundaries": list(boundaries), "first_step": first_step}
    for name, value in values.items():
        key = f"{name}_verdict"
        if key not in verdicts:
            verdicts[key] = OK if value else None
    return JudgeResult(type_key=type_key, **values, **verdicts)


GOOD_CARD = dict(
    type_key="write",
    deliverable="מייל למנהל על הסטטוס, שנשלח",
    done_tests=["המייל נשלח למנהל?"],
    boundaries=["לא כולל קביעת פגישה"],
    first_step="לפתוח טיוטה חדשה עם הנושא 'סטטוס'",
)


def question(text="מה בדיוק התוצר?", sample="למשל: קובץ PDF") -> Question:
    return Question(question=text, sample_answer=sample)


def breakdown(n: int = 1) -> Breakdown:
    return Breakdown(subtasks=[f"חלק {i + 1}" for i in range(n)])


def proposal(*minutes: int) -> Proposal:
    """A model estimate for the whole task: the parts given are just summed."""
    return Proposal(minutes=sum(minutes), rationale="הערכה")


def make_gateway(session_factory, cap: float = 10.0, debug: bool = False):
    from task_compass.config import Settings

    fake = FakeClient()
    settings = Settings(anthropic_api_key="", monthly_cost_cap_usd=cap, debug_log_calls=debug)
    return fake, Gateway(fake, session_factory, settings)
