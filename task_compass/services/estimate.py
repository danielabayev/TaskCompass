"""Time estimate: breakdown, blind estimate, model proposal, clarification round, binding estimate.

Order: the task is first broken into subtasks (the model proposes, the person
edits and confirms). Then the person estimates the whole task in one number (the
blind estimate); the subtasks only help them think. It is saved and locked BEFORE the model's proposal is requested
or shown, and never overwritten.
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
    """Which form the estimate screen shows:
    breakdown_start | breakdown | blind | pending | clarify | binding."""
    if task.blind_estimate_min is None:
        if task.breakdown is None:
            return "breakdown_start"
        return "blind" if task.breakdown_confirmed else "breakdown"
    if task.model_estimate_min is None:
        return "pending"
    if task.needed_clarification and not task.clarifications:
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

    def propose_breakdown(self, task_id: int) -> None:
        """Ask the model for the first list of subtasks (titles only)."""
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.ESTIMATE)
            if estimate_step(task) != "breakdown_start":
                raise FlowError(texts_he.ERROR_WRONG_STAGE)
            card = card_of(task)
        result = self.gateway.breakdown(task_id=task_id, card=card)
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.ESTIMATE)
            task.breakdown = [t.strip() for t in result.subtasks if t.strip()]

    def edit_breakdown(self, task_id: int, titles: list[str], action: str) -> None:
        """Save the person's edits to the subtask list and apply one action:
        add (an empty row), remove:<index>, confirm (locks the list), or save."""
        titles = [(t or "").strip() for t in titles]
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.ESTIMATE)
            if estimate_step(task) != "breakdown":
                raise FlowError(texts_he.ERROR_WRONG_STAGE)
            if action == "add":
                titles.append("")
            elif action.startswith("remove:"):
                index = int(action.split(":", 1)[1]) if action[7:].isdigit() else -1
                if 0 <= index < len(titles):
                    del titles[index]
            elif action == "confirm":
                titles = [t for t in titles if t]
                if not titles:
                    raise FlowError(texts_he.ERROR_BREAKDOWN_EMPTY)
                task.breakdown_confirmed = True
            task.breakdown = titles

    def submit_blind(self, task_id: int, raw_minutes) -> None:
        minutes = require_minutes(raw_minutes)
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.ESTIMATE)
            if task.blind_estimate_min is not None:
                raise FlowError(texts_he.ERROR_BLIND_LOCKED)
            if estimate_step(task) != "blind":
                raise FlowError(texts_he.ERROR_WRONG_STAGE)
            task.blind_estimate_min = minutes
        self._propose(task_id, clarifications=[])

    def retry(self, task_id: int) -> None:
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.ESTIMATE)
            step = estimate_step(task)
            clarifications = list(task.clarifications or [])
        if step == "breakdown_start":
            self.propose_breakdown(task_id)
        elif step == "pending":
            self._propose(task_id, clarifications)

    def clarify(self, task_id: int, text: str) -> None:
        """Add a clarification round and get a new proposal. Required once when
        the gap is 2x or more; after that the person may ask for more rounds
        before setting the binding estimate."""
        text = (text or "").strip()
        if not text:
            raise FlowError(texts_he.ERROR_EMPTY_INPUT)
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.ESTIMATE)
            if estimate_step(task) not in ("clarify", "binding"):
                raise FlowError(texts_he.ERROR_WRONG_STAGE)
            task.clarifications = [*(task.clarifications or []), text]
            clarifications = list(task.clarifications)
            # The proposal is redone with the clarification; clear it first so a
            # failed call leaves the task visibly pending, not half-updated.
            task.model_estimate_min = None
        self._propose(task_id, clarifications)

    def set_binding(self, task_id: int, raw_minutes) -> None:
        minutes = require_minutes(raw_minutes)
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.ESTIMATE)
            if estimate_step(task) != "binding":
                raise FlowError(texts_he.ERROR_WRONG_STAGE)
            task.binding_estimate_min = minutes
            task.status = TaskStatus.PLANNED

    def _propose(self, task_id: int, clarifications: list[str]) -> None:
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id)
            card, subtasks = card_of(task), list(task.breakdown)
        proposal = self.gateway.propose(task_id=task_id, card=card, subtasks=subtasks,
                                        clarifications=clarifications)
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.ESTIMATE)
            task.model_estimate_min = proposal.minutes
            if not clarifications:  # the 2x check runs on the first proposal only
                task.needed_clarification = estimates.needs_clarification(
                    task.blind_estimate_min, task.model_estimate_min)
            cal = calibration.factor_for(task.category.key, calibration_samples(session))
            task.calibration_factor, task.calibration_source = cal.factor, cal.source
            task.corrected_estimate_min = estimates.corrected_estimate(task.blind_estimate_min, cal.factor)
