"""Focus mode for the browser extension: while a task is running, sites that do
not help it are blocked.

The extension sends only domains and page titles. The model judges each domain
once per task; the verdict is stored, so the same site is not judged twice. The
person can override a block ("I need this site"). When the model cannot be
reached, nothing is blocked.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import sessionmaker

from task_compass import config
from task_compass.db import session_scope
from task_compass.interview.service import card_of
from task_compass.llm.gateway import Gateway, LLMError
from task_compass.models import SiteVerdict, Task, TaskStatus

IN_PROGRESS = (TaskStatus.RUNNING, TaskStatus.CHECKPOINT)
MAX_SITES = 50
MAX_TITLE = 120
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}  # the tool itself is never blocked


def normalize_domain(raw) -> str | None:
    host = str(raw or "").strip().lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host or host in LOCAL_HOSTS or host.endswith(".localhost") or len(host) > 255:
        return None
    return host


def _active_task(session) -> Task | None:
    """The task in progress (the most recently started, if there are several). Focus stays on
    when the time runs out (checkpoint) and lifts only when the task is finished or stopped."""
    return session.scalars(
        select(Task).where(Task.status.in_(IN_PROGRESS), Task.user_id == config.USER_ID)
        .order_by(Task.started_at.desc()).limit(1)
    ).first()


def _task_for_model(task: Task) -> dict:
    return {**card_of(task), "opening_text": task.opening_text, "subtasks": list(task.breakdown or [])}


def _sites(session, task_id: int) -> list[dict]:
    """Every judged site of the task: state is blocked | allowed (useful) | allowed_by_user."""
    rows = session.scalars(
        select(SiteVerdict).where(SiteVerdict.task_id == task_id).order_by(SiteVerdict.domain)
    ).all()
    return [{"domain": r.domain, "reason": r.reason or "",
             "state": "blocked" if r.blocked else ("allowed_by_user" if r.allowed_by_user else "allowed")}
            for r in rows]


class FocusService:
    def __init__(self, gateway: Gateway, session_factory: sessionmaker):
        self.gateway = gateway
        self.session_factory = session_factory

    def status(self) -> dict:
        """Whether focus is on, and the sites to block. No running task = nothing blocked."""
        with session_scope(self.session_factory) as session:
            task = _active_task(session)
            if task is None:
                return {"active": False, "task_id": None, "task_title": None, "blocked": []}
            sites = _sites(session, task.id)
            return {"active": True, "task_id": task.id, "task_title": task.title,
                    "blocked": [s for s in sites if s["state"] == "blocked"], "sites": sites}

    def judge_history(self, sites: list[dict]) -> dict:
        """Judge the recent sites that have no verdict yet; answer with the status."""
        try:
            self._judge(sites)
        except LLMError as exc:
            return {**self.status(), "error": exc.message_he}
        return self.status()

    def check(self, domain, title: str = "") -> dict:
        """One site the person just opened: {active, blocked, reason}."""
        host = normalize_domain(domain)
        with session_scope(self.session_factory) as session:
            task = _active_task(session)
            if task is None or host is None:
                return {"active": task is not None, "blocked": False, "reason": ""}
        try:
            self._judge([{"domain": host, "title": title}])
        except LLMError as exc:
            return {"active": True, "blocked": False, "reason": "", "error": exc.message_he}  # fail open
        with session_scope(self.session_factory) as session:
            task = _active_task(session)
            row = task and session.scalars(
                select(SiteVerdict).where(SiteVerdict.task_id == task.id, SiteVerdict.domain == host)
            ).first()
            if row is None:
                return {"active": task is not None, "blocked": False, "reason": ""}
            return {"active": True, "blocked": row.blocked, "reason": row.reason or ""}

    def allow(self, domain) -> dict:
        """The way out: let this site through for the rest of the task."""
        host = normalize_domain(domain)
        with session_scope(self.session_factory) as session:
            task = _active_task(session)
            if task is not None and host is not None:
                session.execute(
                    insert(SiteVerdict).values(
                        user_id=config.USER_ID, task_id=task.id, domain=host, useful=False,
                        reason=None, allowed_by_user=True,
                    ).on_conflict_do_update(
                        index_elements=["task_id", "domain"], set_={"allowed_by_user": True}
                    )
                )
        return self.status()

    # --- internals ------------------------------------------------------

    def _judge(self, sites: list[dict]) -> None:
        wanted: dict[str, str] = {}
        for site in sites[:MAX_SITES]:
            host = normalize_domain(site.get("domain")) if isinstance(site, dict) else None
            if host and host not in wanted:
                wanted[host] = str(site.get("title") or "")[:MAX_TITLE]
        if not wanted:
            return
        with session_scope(self.session_factory) as session:
            task = _active_task(session)
            if task is None:
                return
            task_id, card = task.id, _task_for_model(task)
            known = set(session.scalars(select(SiteVerdict.domain).where(SiteVerdict.task_id == task_id)))
        todo = [{"domain": d, "title": t} for d, t in wanted.items() if d not in known]
        if not todo:
            return
        result = self.gateway.judge_sites(task_id=task_id, task=card, sites=todo)
        by_domain = {v.domain.strip().lower(): v for v in result.sites}
        with session_scope(self.session_factory) as session:
            if session.get(Task, task_id).status not in IN_PROGRESS:
                return  # the task ended while the model was thinking
            for item in todo:
                verdict = by_domain.get(item["domain"])
                if verdict is None:
                    continue
                session.execute(
                    insert(SiteVerdict).values(
                        user_id=config.USER_ID, task_id=task_id, domain=item["domain"],
                        useful=verdict.useful, reason=verdict.reason[:500],
                    ).on_conflict_do_nothing(index_elements=["task_id", "domain"])
                )
