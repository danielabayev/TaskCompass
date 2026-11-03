"""The model sees its own track record: past proposals next to the real time."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from task_compass.models import Category, Task, TaskOutcome
from task_compass.services.estimate import model_history


def _done(session, key, proposed, actual, age_days):
    cat = session.scalars(select(Category).where(Category.key == key)).one()
    session.add(Task(opening_text="x", category_id=cat.id, outcome=TaskOutcome.COMPLETED,
                     model_estimate_min=proposed, actual_min=actual,
                     finished_at=datetime.now(timezone.utc) - timedelta(days=age_days)))


def test_history_lists_same_type_first_with_ratio(session):
    _done(session, "fix", 30, 90, age_days=1)
    _done(session, "build", 60, 60, age_days=2)
    session.commit()
    rows = model_history(session, "build")
    assert [r["type_key"] for r in rows] == ["build", "fix"]
    assert rows[1]["actual_vs_estimate"] == 3.0


def test_history_skips_tasks_without_a_proposal_or_actual(session):
    _done(session, "fix", None, 90, age_days=1)
    session.commit()
    assert model_history(session, "fix") == []
