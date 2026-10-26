"""Database tables (SQLAlchemy). The tables are the single source of truth.

Every table has a constant `user_id` (see config.USER_ID) so more users can
be added later without a data migration.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from task_compass.config import USER_ID


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserOwned:
    user_id: Mapped[int] = mapped_column(Integer, default=USER_ID, index=True)


class Category(UserOwned, Base):
    """A task type (build, fix, learn, ...). A table, not an enum, so the
    future category review can add, merge and retire types."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40))
    name_he: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TaskStatus:
    """Where a task is in the flow. Stored as a plain string."""

    INTERVIEW = "interview"  # Grill Me interview in progress
    STUCK = "stuck"  # 12 rounds without a ready card: split or investigate
    ESTIMATE = "estimate"  # card is ready, collecting the estimates
    PLANNED = "planned"  # binding estimate set, not started
    RUNNING = "running"  # timer running
    CHECKPOINT = "checkpoint"  # time ran out, waiting for the checkpoint
    RETRO = "retro"  # finished or stopped, waiting for the retrospective
    CLOSED = "closed"  # done; see Task.outcome


class TaskOutcome:
    COMPLETED = "completed"
    STOPPED = "stopped"
    SPLIT = "split"  # replaced by child tasks
    INVESTIGATE = "investigate"  # parked; a child investigation task was opened


class Task(UserOwned, Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.INTERVIEW)
    outcome: Mapped[str | None] = mapped_column(String(20))
    opening_text: Mapped[str] = mapped_column(Text)

    # The task card.
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    deliverable: Mapped[str | None] = mapped_column(Text)
    done_tests: Mapped[list] = mapped_column(JSONB, default=list)
    boundaries: Mapped[list] = mapped_column(JSONB, default=list)
    first_step: Mapped[str | None] = mapped_column(Text)
    # Per-field result: {"deliverable": {"status": "pass"|"fail"|"unchecked", "reason": "..."}}
    verdicts: Mapped[dict] = mapped_column(JSONB, default=dict)

    # The four estimate values, in minutes. The blind estimate is never overwritten.
    blind_estimate_min: Mapped[int | None] = mapped_column(Integer)
    model_estimate_min: Mapped[int | None] = mapped_column(Integer)
    model_breakdown: Mapped[list | None] = mapped_column(JSONB)
    corrected_estimate_min: Mapped[int | None] = mapped_column(Integer)
    calibration_factor: Mapped[float | None] = mapped_column(Float)
    calibration_source: Mapped[str | None] = mapped_column(String(10))
    binding_estimate_min: Mapped[int | None] = mapped_column(Integer)
    clarification_note: Mapped[str | None] = mapped_column(Text)
    needed_clarification: Mapped[bool] = mapped_column(Boolean, default=False)

    # Execution.
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extension_min: Mapped[int] = mapped_column(Integer, default=0)
    scope_reduced: Mapped[bool] = mapped_column(Boolean, default=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_min: Mapped[int | None] = mapped_column(Integer)
    shortened_in_hindsight: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    category: Mapped[Category | None] = relationship()
    parent: Mapped["Task | None"] = relationship(remote_side=[id])
    turns: Mapped[list["InterviewTurn"]] = relationship(
        order_by="InterviewTurn.round_no", back_populates="task"
    )
    checkpoints: Mapped[list["Checkpoint"]] = relationship(order_by="Checkpoint.id")
    retro: Mapped["Retro | None"] = relationship(uselist=False)

    @property
    def title(self) -> str:
        """Short label for lists: the deliverable once known, else the opening text."""
        return self.deliverable or self.opening_text


class InterviewTurn(UserOwned, Base):
    """One question and its answer. Round numbers start at 1."""

    __tablename__ = "interview_turns"
    __table_args__ = (UniqueConstraint("task_id", "round_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    round_no: Mapped[int] = mapped_column(Integer)
    field: Mapped[str] = mapped_column(String(20))  # the card field the question targets
    question: Mapped[str] = mapped_column(Text)
    sample_answer: Mapped[str | None] = mapped_column(Text)
    # Shown above the question, e.g. the missing-fields list after "enough".
    note: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped[Task] = relationship(back_populates="turns")


class Checkpoint(UserOwned, Base):
    """What happened when the time ran out, and how the user chose to continue."""

    __tablename__ = "checkpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    done_tests_met: Mapped[list] = mapped_column(JSONB, default=list)  # list of bools
    remaining_and_surprise: Mapped[str | None] = mapped_column(Text)
    delay_cause: Mapped[str | None] = mapped_column(Text)
    choice: Mapped[str] = mapped_column(String(10))  # extend | split | reduce | stop
    extension_min: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Retro(UserOwned, Base):
    __tablename__ = "retros"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(10))  # short | deep
    direction: Mapped[str] = mapped_column(String(10))  # on | over | under
    deviation_ratio: Mapped[float | None] = mapped_column(Float)  # actual / binding
    too_simple: Mapped[bool | None] = mapped_column(Boolean)
    cause: Mapped[str | None] = mapped_column(Text)
    definition_gap: Mapped[str | None] = mapped_column(Text)
    lesson: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LlmCall(UserOwned, Base):
    """One model call: tokens, cost and result. Never stores the key or the prompt."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(60))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    success: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
