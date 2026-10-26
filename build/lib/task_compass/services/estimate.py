"""Time estimate: blind estimate, model proposal, clarification round, binding estimate.

Order: the blind estimate is saved and locked BEFORE the model's proposal is
requested or shown. It is never overwritten.
"""

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from task_compass import texts_he
from task_compass.db import session_scope
from task_compass.domain import calibration, estimates
from task_compass.errors import FlowError
from task_compass.interview.service import card_of
from task_compass.llm.gateway import Gateway
from task_compass.models import Category, Task, TaskOutcome, TaskStatus
from task_compass.services.common import get_task, require_minutes


def estimate_step(task: Task) -> str:
    """Which form the estimate screen shows: blind | pending | clarify | binding."""
    if task.blind_estimate_min is None:
        return "blind"
    if task.model_estimate_min is None:
        return "pending"
    if task.needed_clarification and task.clarification_note is None:
        return "clarify"
    return "binding"


def calibration_samples(session) -> list[calibration.Sample]:
    """Completed tasks with an actual time, newest first."""
    rows = session.execute(
        select(Category.key, Task.blind_estimate_min, Task.actual_min)
        .join(Category, Category.id == Task.category_id)
        .where(Task.outcome == TaskOutcome.COMPLETED, Task.actual_min.is_not(None),
               Task.blind_estimate_min.is_not(None))
        .order_by(Task.finished_at.desc())
    ).all()
    return [calibration.Sample(*row) for row in rows]


class EstimateService:
    def __init__(self, gateway: Gateway, session_factory: sessionmaker):
        self.gateway = gateway
        self.session_factory = session_factory

    def submit_blind(self, task_id: int, raw_minutes) -> None:
        minutes = require_minutes(raw_minutes)
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.ESTIMATE)
            if task.blind_estimate_min is not None:
                raise FlowError(texts_he.ERROR_BLIND_LOCKED)
            task.blind_estimate_min = minutes
        self._propose(task_id, clarification=None)

    def retry(self, task_id: int) -> None:
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.ESTIMATE)
            step = estimate_step(task)
            clarification = task.clarification_note
        if step == "pending":
            self._propose(task_id, clarification)

    def clarify(self, task_id: int, text: str) -> None:
        text = (text or "").strip()
        if not text:
            raise FlowError(texts_he.ERROR_EMPTY_INPUT)
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.ESTIMATE)
            if estimate_step(task) != "clarify":
                raise FlowError(texts_he.ERROR_WRONG_STAGE)
            task.clarification_note = text
            # The proposal is redone with the clarification; clear it first so a
            # failed call leaves the task visibly pending, not half-updated.
            task.model_estimate_min = None
            task.model_breakdown = None
        self._propose(task_id, text)

    def set_binding(self, task_id: int, raw_minutes) -> None:
        minutes = require_minutes(raw_minutes)
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.ESTIMATE)
            if estimate_step(task) != "binding":
                raise FlowError(texts_he.ERROR_WRONG_STAGE)
            task.binding_estimate_min = minutes
            task.status = TaskStatus.PLANNED

    def _propose(self, task_id: int, clarification: str | None) -> None:
        with session_scope(self.session_factory) as session:
            card = card_of(get_task(session, task_id))
        proposal = self.gateway.propose(task_id=task_id, card=card, clarification=clarification)
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.ESTIMATE)
            task.model_breakdown = [s.model_dump() for s in proposal.subtasks]
            task.model_estimate_min = sum(s.minutes for s in proposal.subtasks)
            if clarification is None:
                task.needed_clarification = estimates.needs_clarification(
                    task.blind_estimate_min, task.model_estimate_min)
            cal = calibration.factor_for(task.category.key, calibration_samples(session))
            task.calibration_factor, task.calibration_source = cal.factor, cal.source
            task.corrected_estimate_min = estimates.corrected_estimate(task.blind_estimate_min, cal.factor)
