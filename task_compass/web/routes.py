"""HTTP routes. Every task screen is one "stage" block that HTMX swaps in place.

POST routes do one action and answer with the re-rendered stage (for HTMX),
or redirect to the task page (plain form post). Errors are shown inside the
stage with the person's input kept.
"""

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for
from sqlalchemy import select

from task_compass import config, texts_he
from task_compass.db import session_scope
from task_compass.domain import execution
from task_compass.errors import FlowError
from task_compass.interview.service import is_pending, open_turn
from task_compass.llm.gateway import LLMError
from task_compass.models import Category, Task, TaskStatus
from task_compass.services import reports
from task_compass.services.estimate import estimate_step
from task_compass.services.execution import deadline_of
from task_compass.services.retro import plan_for

bp = Blueprint("web", __name__)


def services():
    return current_app.extensions["task_compass"]


# --- pages ----------------------------------------------------------------------

@bp.get("/")
def home():
    return render_template("home.html", tasks=_open_tasks())


def _open_tasks() -> list[Task]:
    with session_scope(services().session_factory) as session:
        return session.scalars(
            select(Task).where(Task.status != TaskStatus.CLOSED).order_by(Task.updated_at.desc())
        ).all()


@bp.post("/tasks")
def create_task():
    try:
        task_id = services().interview.start(request.form.get("opening", ""))
    except FlowError as exc:
        return render_template("home.html", tasks=_open_tasks(), error=exc.message_he), 400
    except LLMError as exc:
        # The task exists and is pending: show it with the error and a retry button.
        return _render(exc.task_id, full_page=True, error=exc.message_he)
    return redirect(url_for("web.task_page", task_id=task_id))


@bp.get("/tasks/<int:task_id>")
def task_page(task_id: int):
    if not _exists(task_id):
        abort(404)
    services().execution.refresh(task_id)
    return _render(task_id, full_page=True)


@bp.get("/tasks/<int:task_id>/stage")
def stage(task_id: int):
    """Polled by the timer when time runs out."""
    if not _exists(task_id):
        abort(404)
    services().execution.refresh(task_id)
    return _render(task_id)


@bp.get("/history")
def history():
    with session_scope(services().session_factory) as session:
        return render_template("history.html", tasks=reports.history(session))


@bp.get("/spend")
def spend():
    with session_scope(services().session_factory) as session:
        return render_template("spend.html", spend=reports.spend(session, services().settings))


# --- actions --------------------------------------------------------------------

def _action(task_id: int, fn):
    """Run one action and answer with the updated stage, or the stage plus an error."""
    if not _exists(task_id):
        abort(404)
    try:
        fn()
    except (FlowError, LLMError) as exc:
        return _render(task_id, full_page=not _htmx(), error=exc.message_he, form=request.form)
    if _htmx():
        return _render(task_id)
    return redirect(url_for("web.task_page", task_id=task_id))


def _htmx() -> bool:
    return bool(request.headers.get("HX-Request"))


@bp.post("/tasks/<int:task_id>/answer")
def answer(task_id: int):
    round_no = request.form.get("round", type=int)
    return _action(task_id, lambda: services().interview.answer(task_id, request.form.get("answer", ""), round_no))


@bp.post("/tasks/<int:task_id>/retry")
def retry(task_id: int):
    def run():
        with session_scope(services().session_factory) as session:
            status = session.get(Task, task_id).status
        if status == TaskStatus.ESTIMATE:
            services().estimate.retry(task_id)
        else:
            services().interview.retry(task_id)
    return _action(task_id, run)


@bp.post("/tasks/<int:task_id>/type")
def change_type(task_id: int):
    return _action(task_id, lambda: services().interview.change_type(task_id, request.form.get("type_key", "")))


@bp.post("/tasks/<int:task_id>/stuck")
def resolve_stuck(task_id: int):
    if not _exists(task_id):
        abort(404)
    try:
        child_id = services().interview.resolve_stuck(
            task_id, request.form.get("choice", ""), request.form.get("child", ""))
    except FlowError as exc:
        return _render(task_id, full_page=not _htmx(), error=exc.message_he, form=request.form)
    except LLMError as exc:
        child_id = exc.task_id  # the child exists and is pending
    return _redirect(url_for("web.task_page", task_id=child_id))


@bp.post("/tasks/<int:task_id>/blind")
def blind(task_id: int):
    return _action(task_id, lambda: services().estimate.submit_blind(task_id, request.form.get("minutes")))


@bp.post("/tasks/<int:task_id>/clarify")
def clarify(task_id: int):
    return _action(task_id, lambda: services().estimate.clarify(task_id, request.form.get("clarification", "")))


@bp.post("/tasks/<int:task_id>/binding")
def binding(task_id: int):
    return _action(task_id, lambda: services().estimate.set_binding(task_id, request.form.get("minutes")))


@bp.post("/tasks/<int:task_id>/start")
def start(task_id: int):
    return _action(task_id, lambda: services().execution.start(task_id))


@bp.post("/tasks/<int:task_id>/finish")
def finish(task_id: int):
    return _action(task_id, lambda: services().execution.finish(task_id))


@bp.post("/tasks/<int:task_id>/checkpoint")
def checkpoint(task_id: int):
    form = request.form

    def run():
        with session_scope(services().session_factory) as session:
            count = len(session.get(Task, task_id).done_tests or [])
        services().execution.checkpoint(
            task_id,
            done_tests_met=[f"met_{i}" in form for i in range(count)],
            remaining_and_surprise=form.get("remaining", ""),
            delay_cause=form.get("cause", ""),
            choice=form.get("choice", ""),
            extension_min=form.get("extend_minutes") if form.get("choice") == "extend" else form.get("reduce_minutes"),
            done_tests_text=form.get("reduce_tests", ""),
            children_text=form.get("children", ""),
        )
    return _action(task_id, run)


@bp.post("/tasks/<int:task_id>/retro")
def retro(task_id: int):
    form = request.form
    too_simple = {"yes": True, "no": False}.get(form.get("too_simple", ""))
    return _action(task_id, lambda: services().retro.submit(
        task_id, cause=form.get("cause", ""), definition_gap=form.get("definition_gap", ""),
        lesson=form.get("lesson", ""), too_simple=too_simple, hindsight_min=form.get("hindsight")))


# --- rendering ------------------------------------------------------------------

def _exists(task_id: int) -> bool:
    with session_scope(services().session_factory) as session:
        return session.get(Task, task_id) is not None


def _redirect(url: str):
    """Navigate to another page, also from inside an HTMX request."""
    if _htmx():
        return "", 204, {"HX-Redirect": url}
    return redirect(url)


def _render(task_id: int, *, full_page: bool = False, error: str | None = None, form=None):
    with session_scope(services().session_factory) as session:
        task = session.get(Task, task_id)
        ctx = {
            "task": task,
            "error": error,
            "form": form or {},
            "turn": open_turn(task),
            "pending": is_pending(task),
            "rounds_answered": sum(1 for t in task.turns if t.answer is not None),
            "categories": session.scalars(select(Category).where(Category.active).order_by(Category.id)).all(),
            "children": session.scalars(select(Task).where(Task.parent_id == task.id).order_by(Task.id)).all(),
        }
        if task.status == TaskStatus.ESTIMATE:
            ctx["estimate_step"] = estimate_step(task)
        if task.status in (TaskStatus.RUNNING, TaskStatus.CHECKPOINT):
            ctx["deadline"] = deadline_of(task)
            ctx["allowed_choices"] = execution.allowed_choices([c.choice for c in task.checkpoints])
        if task.status == TaskStatus.RETRO or (task.retro and task.actual_min):
            ctx["retro_plan"] = plan_for(task)
        template = "task.html" if full_page else "partials/stage.html"
        # HTMX only swaps 2xx answers, so an error inside the stage is still a 200.
        status = 400 if error and full_page else 200
        return render_template(template, **ctx), status


@bp.app_context_processor
def inject_texts():
    return {"ui": texts_he.UI, "t": texts_he, "max_rounds": config.MAX_INTERVIEW_ROUNDS}
