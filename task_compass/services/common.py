"""Small helpers shared by the services."""

from datetime import datetime, timezone

from task_compass import texts_he
from task_compass.errors import FlowError
from task_compass.models import Task


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_task(session, task_id: int, *statuses: str) -> Task:
    """Load a task and check it is in one of the given statuses (if any)."""
    task = session.get(Task, task_id)
    if task is None:
        raise FlowError(texts_he.ERROR_NOT_FOUND)
    if statuses and task.status not in statuses:
        raise FlowError(texts_he.ERROR_WRONG_STAGE)
    return task


def require_minutes(raw) -> int:
    from task_compass.domain.estimates import parse_minutes

    minutes = parse_minutes(raw)
    if minutes is None:
        raise FlowError(texts_he.ERROR_MINUTES)
    return minutes
