"""Execution: the timer, the checkpoint when time runs out, and finishing.

The start time lives in the database, so refreshing the page or restarting
the server never resets the timer.
"""

from datetime import datetime

from sqlalchemy.orm import sessionmaker

from task_compass import texts_he
from task_compass.db import session_scope
from task_compass.domain import execution
from task_compass.errors import FlowError
from task_compass.models import Checkpoint, Task, TaskOutcome, TaskStatus
from task_compass.services.common import get_task, now_utc, require_minutes


def deadline_of(task: Task) -> datetime:
    return execution.deadline(task.started_at, task.binding_estimate_min, task.extension_min)


def _lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


class ExecutionService:
    def __init__(self, session_factory: sessionmaker, retro_service):
        self.session_factory = session_factory
        self.retro = retro_service

    def start(self, task_id: int) -> None:
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.PLANNED)
            task.started_at = now_utc()
            task.status = TaskStatus.RUNNING

    def refresh(self, task_id: int, now: datetime | None = None) -> None:
        """Move a running task to the checkpoint once its time is up."""
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id)
            if task.status == TaskStatus.RUNNING and execution.is_overdue(
                now or now_utc(), task.started_at, task.binding_estimate_min, task.extension_min
            ):
                task.status = TaskStatus.CHECKPOINT

    def finish(self, task_id: int) -> None:
        """The person finished the task (on time or late)."""
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.RUNNING, TaskStatus.CHECKPOINT)
            self._end(task, TaskOutcome.COMPLETED)
        self.retro.close_if_short(task_id)

    def checkpoint(self, task_id: int, *, done_tests_met: list[bool], remaining_and_surprise: str,
                   delay_cause: str, choice: str, extension_min=None, done_tests_text: str = "",
                   children_text: str = "") -> list[int]:
        """Record the checkpoint answers and apply the chosen way to continue.
        Returns the ids of child tasks created by a split."""
        children: list[int] = []
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id, TaskStatus.CHECKPOINT)
            try:
                execution.check_choice(choice, [c.choice for c in task.checkpoints])
            except execution.ExtensionNotAllowed:
                raise FlowError(texts_he.ERROR_SECOND_EXTENSION)
            except ValueError:
                raise FlowError(texts_he.ERROR_WRONG_STAGE)

            minutes = None
            if choice in (execution.EXTEND, execution.REDUCE):
                minutes = require_minutes(extension_min)
            if choice == execution.REDUCE:
                kept = _lines(done_tests_text)
                if not kept:
                    raise FlowError(texts_he.ERROR_REDUCE_NEEDS_TESTS)
                task.done_tests = kept
                task.scope_reduced = True
            if choice == execution.SPLIT and not _lines(children_text):
                raise FlowError(texts_he.ERROR_SPLIT_NEEDS_CHILDREN)

            session.add(Checkpoint(
                task_id=task.id, done_tests_met=list(done_tests_met),
                remaining_and_surprise=remaining_and_surprise.strip() or None,
                delay_cause=delay_cause.strip() or None, choice=choice, extension_min=minutes,
            ))
            if minutes:
                task.extension_min += minutes
                task.status = TaskStatus.RUNNING
            elif choice == execution.SPLIT:
                self._end(task, TaskOutcome.SPLIT)
                for line in _lines(children_text):
                    child = Task(opening_text=line, parent_id=task.id)
                    session.add(child)
                    session.flush()
                    children.append(child.id)
            else:  # stop
                self._end(task, TaskOutcome.STOPPED)
        return children

    @staticmethod
    def _end(task: Task, outcome: str) -> None:
        task.finished_at = now_utc()
        task.actual_min = execution.elapsed_minutes(task.started_at, task.finished_at)
        task.outcome = outcome
        task.status = TaskStatus.RETRO
