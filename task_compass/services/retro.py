"""The retrospective, adapted to the deviation from the binding estimate."""

from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker

from task_compass import texts_he
from task_compass.db import session_scope
from task_compass.domain import breakdown_review, retro
from task_compass.errors import FlowError
from task_compass.models import Retro, Task, TaskOutcome, TaskStatus
from task_compass.services.common import get_task, require_minutes


@dataclass(frozen=True)
class RetroPlan:
    ratio: float
    direction: str  # on | over | under
    kind: str  # short | deep
    ask_too_simple: bool  # finished well under the estimate


def plan_for(task: Task) -> RetroPlan:
    ratio = retro.deviation_ratio(task.actual_min, task.binding_estimate_min)
    unusual = bool(task.checkpoints) or bool(task.clarifications) or task.scope_reduced \
        or task.outcome in (TaskOutcome.STOPPED, TaskOutcome.SPLIT)
    direction = retro.direction(ratio)
    return RetroPlan(
        ratio=ratio, direction=direction, kind=retro.retro_kind(ratio, unusual),
        ask_too_simple=direction == retro.UNDER and task.outcome == TaskOutcome.COMPLETED,
    )


def review_pending(task: Task) -> bool:
    """A task that had a confirmed breakdown is reviewed once, before the retrospective."""
    return bool(task.status == TaskStatus.RETRO and task.breakdown_confirmed and task.breakdown
                and task.breakdown_review is None)


class RetroService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def close_if_short(self, task_id: int) -> bool:
        """On estimate and nothing unusual: save the numbers and close, no questions."""
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.RETRO)
            plan = plan_for(task)
            if plan.kind != retro.SHORT or review_pending(task):
                return False
            session.add(Retro(task_id=task.id, kind=plan.kind, direction=plan.direction,
                              deviation_ratio=plan.ratio))
            task.status = TaskStatus.CLOSED
            return True

    def submit_breakdown_review(self, task_id: int, verdicts: list[str], missing_text: str) -> None:
        """Save the verdict on each subtask and the missing ones; a short retro then closes by itself."""
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.RETRO)
            if not review_pending(task):
                raise FlowError(texts_he.ERROR_WRONG_STAGE)
            try:
                task.breakdown_review = breakdown_review.build_review(list(task.breakdown), verdicts, missing_text)
            except ValueError:
                raise FlowError(texts_he.ERROR_REVIEW_INCOMPLETE)
        self.close_if_short(task_id)

    def submit(self, task_id: int, *, cause: str, definition_gap: str, lesson: str,
               too_simple: bool | None = None, hindsight_min=None) -> None:
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.RETRO)
            if review_pending(task):
                raise FlowError(texts_he.ERROR_WRONG_STAGE)
            plan = plan_for(task)
            if too_simple and plan.ask_too_simple:
                try:
                    task.actual_min = retro.hindsight_actual(task.actual_min, require_minutes(hindsight_min))
                except ValueError:
                    raise FlowError(texts_he.ERROR_HINDSIGHT)
                task.shortened_in_hindsight = True
            session.add(Retro(
                task_id=task.id, kind=plan.kind, direction=plan.direction, deviation_ratio=plan.ratio,
                too_simple=too_simple if plan.ask_too_simple else None,
                cause=cause.strip() or None, definition_gap=definition_gap.strip() or None,
                lesson=lesson.strip() or None,
            ))
            task.status = TaskStatus.CLOSED
