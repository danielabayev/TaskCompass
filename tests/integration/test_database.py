"""Phase 0 checkpoint: the migrated database is reachable and seeded."""

from sqlalchemy import select

from task_compass.models import Category, Task


def test_categories_are_seeded(session):
    keys = set(session.scalars(select(Category.key)))
    assert keys == {"build", "fix", "learn", "write", "decide", "errands"}


def test_task_round_trip_has_constant_user_id(session):
    task = Task(opening_text="לסדר את המחסן")
    session.add(task)
    session.commit()
    stored = session.get(Task, task.id)
    assert stored.user_id == 1
    assert stored.done_tests == [] and stored.status == "interview"
