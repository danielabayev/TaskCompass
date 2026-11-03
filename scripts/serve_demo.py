"""A demo copy of the app for checking screens in a browser, with no model calls.

It runs on the TEST database (never your real one) with a scripted fake model, and
seeds one task per screen worth looking at. Every start wipes and re-seeds it.

    uv run python -m scripts.serve_demo            # http://127.0.0.1:5055
"""

from sqlalchemy import text

from task_compass import config
from task_compass.config import Settings
from task_compass.db import get_engine, make_session_factory
from task_compass.llm.fake import FakeClient
from task_compass.models import Category, Task
from task_compass.web import create_app
from task_compass.wiring import build_services

PORT = 5055
LONG_TITLE = "לכתוב את הטיוטה הראשונה של המסמך המלא כולל כל הסעיפים, הטבלאות וההערות לקוראים, ולשלוח אותה לבדיקה"
CARD = dict(
    deliverable="מייל למנהל על הסטטוס, שנשלח",
    done_tests=["המייל נשלח למנהל?"],
    boundaries=["לא כולל קביעת פגישה"],
    first_step="לפתוח טיוטה חדשה",
    verdicts={k: {"status": "pass", "reason": ""} for k in ("type", "deliverable", "done_tests", "boundaries", "first_step")},
)


def seed(factory) -> None:
    engine = get_engine(config.database_url(test=True))
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE site_verdicts, llm_calls, retros, checkpoints, interview_turns, tasks, task_groups "
                          "RESTART IDENTITY CASCADE"))
    with factory() as s:
        category = s.query(Category).filter_by(key="write").one()
        # 1: the breakdown editor, with a title longer than the box
        s.add(Task(opening_text="לכתוב מייל למנהל", status="estimate", category_id=category.id,
                   breakdown=[LONG_TITLE, "לנסח", "לשלוח"], breakdown_confirmed=False, **CARD))
        s.commit()


def main() -> None:
    factory = make_session_factory(config.database_url(test=True))
    seed(factory)
    services = build_services(FakeClient(), factory, Settings(anthropic_api_key="", monthly_cost_cap_usd=10, debug_log_calls=False))
    create_app(services).run(host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
