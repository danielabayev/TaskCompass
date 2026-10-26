"""Read-only views: task history and the month's model spend."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from task_compass import config
from task_compass.llm.gateway import month_spend
from task_compass.models import LlmCall, Task
from task_compass.services.common import now_utc

ALERT_SHARE = Decimal("0.7")  # warn at 70% of the cap


@dataclass
class Spend:
    total: Decimal
    cap: Decimal
    by_purpose: list[tuple[str, str, int, Decimal]]  # purpose, model, calls, cost
    failed_calls: int

    @property
    def share(self) -> Decimal:
        return self.total / self.cap if self.cap else Decimal(1)

    @property
    def alert(self) -> bool:
        return self.share >= ALERT_SHARE


def history(session) -> list[Task]:
    return list(session.scalars(
        select(Task).options(selectinload(Task.category), selectinload(Task.retro))
        .order_by(Task.created_at.desc())
    ))


def spend(session, settings: config.Settings | None = None) -> Spend:
    settings = settings or config.Settings()
    now = now_utc()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    in_month = LlmCall.created_at >= start
    rows = session.execute(
        select(LlmCall.purpose, LlmCall.model, func.count(), func.coalesce(func.sum(LlmCall.cost_usd), 0))
        .where(in_month).group_by(LlmCall.purpose, LlmCall.model).order_by(LlmCall.purpose)
    ).all()
    failed = session.scalar(select(func.count()).where(in_month, LlmCall.success.is_(False)))
    return Spend(month_spend(session, now), Decimal(str(settings.monthly_cost_cap_usd)),
                 [(p, m, n, Decimal(c)) for p, m, n, c in rows], failed)
