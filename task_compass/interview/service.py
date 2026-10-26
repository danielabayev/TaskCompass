"""Loads and saves interview state around one graph step.

Order of work in every request: save the person's input first, then call the
model. If the model call fails, the input is already stored and the task is
"pending": `retry` runs the same step again.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from task_compass import texts_he
from task_compass.db import session_scope
from task_compass.errors import FlowError
from task_compass.interview.graph import build_graph
from task_compass.llm.gateway import Gateway, LLMError
from task_compass.models import Category, InterviewTurn, Retro, Task, TaskOutcome, TaskStatus

HISTORY_TURNS = 6  # earlier Q&A pairs given to the interviewer
LESSONS = 3  # retro lessons from earlier tasks of the same type


def card_of(task: Task) -> dict:
    return {
        "type_key": task.category.key if task.category else None,
        "deliverable": task.deliverable,
        "done_tests": list(task.done_tests or []),
        "boundaries": list(task.boundaries or []),
        "first_step": task.first_step,
    }


def open_turn(task: Task) -> InterviewTurn | None:
    """The question waiting for an answer, if there is one."""
    if task.turns and task.turns[-1].answer is None:
        return task.turns[-1]
    return None


def is_pending(task: Task) -> bool:
    """The person's last input is saved but the model step after it did not complete."""
    return task.status == TaskStatus.INTERVIEW and open_turn(task) is None


class InterviewService:
    def __init__(self, gateway: Gateway, session_factory: sessionmaker):
        self.gateway = gateway
        self.session_factory = session_factory
        self.graph = build_graph(gateway)

    # --- commands -----------------------------------------------------------

    def start(self, opening_text: str, parent_id: int | None = None) -> int:
        """Create a task from its opening text and run the first step.
        Returns the task id even if the model call fails (the task is then pending)."""
        opening_text = opening_text.strip()
        if not opening_text:
            raise FlowError(texts_he.ERROR_EMPTY_INPUT)
        with session_scope(self.session_factory) as session:
            task = Task(opening_text=opening_text, parent_id=parent_id)
            session.add(task)
            session.flush()
            task_id = task.id
        try:
            self._step(task_id)
        except LLMError as exc:
            exc.task_id = task_id  # the task exists and is pending; callers can show it
            raise
        return task_id

    def answer(self, task_id: int, text: str) -> None:
        text = text.strip()
        if not text:
            raise FlowError(texts_he.ERROR_EMPTY_INPUT)
        with session_scope(self.session_factory) as session:
            task = self._task(session, task_id)
            turn = open_turn(task)
            if task.status != TaskStatus.INTERVIEW or turn is None:
                raise FlowError(texts_he.ERROR_WRONG_STAGE)
            turn.answer = text
            turn.answered_at = datetime.now(timezone.utc)
        self._step(task_id)

    def retry(self, task_id: int) -> None:
        with session_scope(self.session_factory) as session:
            if not is_pending(self._task(session, task_id)):
                return
        self._step(task_id)

    def change_type(self, task_id: int, type_key: str) -> None:
        """The person changes the task type. The card is judged again under the
        new type (it decides which done tests are acceptable), and the open
        question is replaced. This does not count as a round."""
        with session_scope(self.session_factory) as session:
            task = self._task(session, task_id)
            if task.status != TaskStatus.INTERVIEW:
                raise FlowError(texts_he.ERROR_WRONG_STAGE)
            category = session.scalar(select(Category).where(Category.key == type_key, Category.active))
            if category is None:
                raise FlowError(texts_he.ERROR_UNKNOWN_TYPE)
            if task.category_id == category.id:
                return
            task.category_id = category.id
            turn = open_turn(task)
            if turn is not None:
                session.delete(turn)
        self._step(task_id, synthetic_answer=texts_he.TYPE_CHANGED_ANSWER.format(type_key))

    def resolve_stuck(self, task_id: int, choice: str, child_opening: str) -> int:
        """After 12 rounds: split off a smaller piece, or open an investigation.
        No partial card is created; the original task is closed with that outcome."""
        if choice not in (TaskOutcome.SPLIT, TaskOutcome.INVESTIGATE):
            raise FlowError(texts_he.ERROR_WRONG_STAGE)
        with session_scope(self.session_factory) as session:
            task = self._task(session, task_id)
            if task.status != TaskStatus.STUCK:
                raise FlowError(texts_he.ERROR_WRONG_STAGE)
            task.status, task.outcome = TaskStatus.CLOSED, choice
            if choice == TaskOutcome.INVESTIGATE and not child_opening.strip():
                child_opening = texts_he.INVESTIGATE_PREFIX + task.opening_text
        return self.start(child_opening, parent_id=task_id)

    # --- the step -----------------------------------------------------------

    def _step(self, task_id: int, synthetic_answer: str | None = None) -> None:
        state = self._load_state(task_id, synthetic_answer)
        result = self.graph.invoke(state)  # may raise LLMError; nothing is saved then
        self._save(task_id, result)

    def _load_state(self, task_id: int, synthetic_answer: str | None) -> dict:
        with session_scope(self.session_factory) as session:
            task = self._task(session, task_id)
            answered = [t for t in task.turns if t.answer is not None]
            if synthetic_answer is not None:
                question, answer = None, synthetic_answer
            elif answered:
                question, answer = answered[-1].question, answered[-1].answer
            else:
                question, answer = None, task.opening_text
            active = dict(session.execute(select(Category.key, Category.name_he).where(Category.active)).all())
            return {
                "task_id": task.id,
                "card": card_of(task),
                "verdicts": dict(task.verdicts or {}),
                "active_types": active,
                "question": question,
                "answer": answer,
                "rounds_answered": len(answered),
                "history": [(t.question, t.answer) for t in answered[-HISTORY_TURNS:]],
                "lessons": self._lessons(session, task),
            }

    def _lessons(self, session, task: Task) -> list[str]:
        if task.category_id is None:
            return []
        rows = session.scalars(
            select(Retro.lesson)
            .join(Task, Task.id == Retro.task_id)
            .where(Task.category_id == task.category_id, Retro.lesson.is_not(None), Task.id != task.id)
            .order_by(Retro.created_at.desc())
            .limit(LESSONS)
        )
        return [r for r in rows if r.strip()]

    def _save(self, task_id: int, result: dict) -> None:
        with session_scope(self.session_factory) as session:
            task = self._task(session, task_id)
            card = result["card"]
            task.category_id = session.scalar(select(Category.id).where(Category.key == card["type_key"])) if card["type_key"] else None
            task.deliverable = card["deliverable"]
            task.done_tests = list(card["done_tests"])
            task.boundaries = list(card["boundaries"])
            task.first_step = card["first_step"]
            task.verdicts = dict(result["verdicts"])
            if result["outcome"] == "ready":
                task.status = TaskStatus.ESTIMATE
            elif result["outcome"] == "stuck":
                task.status = TaskStatus.STUCK
            else:
                last = max((t.round_no for t in task.turns), default=0)
                session.add(InterviewTurn(
                    task_id=task.id, round_no=last + 1, field=result["next_field"],
                    question=result["next_question"], sample_answer=result["sample_answer"],
                    note=result.get("note"),
                ))

    @staticmethod
    def _task(session, task_id: int) -> Task:
        task = session.get(Task, task_id)
        if task is None:
            raise FlowError(texts_he.ERROR_NOT_FOUND)
        return task

