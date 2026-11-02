"""HTTP routes. Every task screen is one "stage" block that HTMX swaps in place.

POST routes do one action and answer with the re-rendered stage (for HTMX),
or redirect to the task page (plain form post). Errors are shown inside the
stage with the person's input kept.
"""

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, url_for
from sqlalchemy import select

from task_compass import config, texts_he
from task_compass.db import session_scope
from task_compass.domain import execution
from task_compass.errors import FlowError
from task_compass.interview.service import is_pending, open_turn
from task_compass.llm.gateway import LLMError
from task_compass.models import Category, LlmCall, Task, TaskStatus
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


@bp.get("/tasks/<int:task_id>/calls")
def task_calls(task_id: int):
    """Every model call for one task, with the prompt and reply when debug logging was on."""
    with session_scope(services().session_factory) as session:
        task = session.get(Task, task_id)
        if task is None:
            abort(404)
        calls = session.scalars(select(LlmCall).where(LlmCall.task_id == task_id).order_by(LlmCall.id)).all()
        return render_template("calls.html", task=task, calls=calls,
                               debug_on=services().settings.debug_log_calls)


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


@bp.post("/tasks/<int:task_id>/breakdown/propose")
def breakdown_propose(task_id: int):
    return _action(task_id, lambda: services().estimate.propose_breakdown(task_id))


@bp.post("/tasks/<int:task_id>/breakdown")
def breakdown(task_id: int):
    return _action(task_id, lambda: services().estimate.edit_breakdown(
        task_id, request.form.getlist("title"), request.form.get("action", "save")))


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


@bp.post("/tasks/<int:task_id>/pause")
def pause(task_id: int):
    return _action(task_id, lambda: services().execution.pause(task_id))


@bp.post("/tasks/<int:task_id>/resume")
def resume(task_id: int):
    return _action(task_id, lambda: services().execution.resume(task_id))


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


# --- manage tasks: delete, nest, group ------------------------------------------------

def _manage_page(error: str | None = None):
    sections = services().manage.tree()

    def flat(nodes):
        for n in nodes:
            yield n.task
            yield from flat(n.children)

    tasks = sorted((t for s in sections for t in flat(s.nodes)), key=lambda t: t.id)
    groups = [s.group for s in sections if s.group]
    return render_template("manage.html", sections=sections, tasks=tasks, groups=groups, error=error), 400 if error else 200


def _manage_action(fn):
    try:
        fn()
    except FlowError as exc:
        return _manage_page(exc.message_he)
    return redirect(url_for("web.manage"))


@bp.get("/manage")
def manage():
    return _manage_page()


@bp.post("/manage/groups")
def manage_create_group():
    return _manage_action(lambda: services().manage.create_group(request.form.get("name", "")))


@bp.post("/manage/groups/<int:group_id>/rename")
def manage_rename_group(group_id: int):
    return _manage_action(lambda: services().manage.rename_group(group_id, request.form.get("name", "")))


@bp.post("/manage/groups/<int:group_id>/delete")
def manage_delete_group(group_id: int):
    return _manage_action(lambda: services().manage.delete_group(group_id))


@bp.post("/manage/tasks/<int:task_id>/delete")
def manage_delete_task(task_id: int):
    return _manage_action(lambda: services().manage.delete_task(task_id))


@bp.post("/manage/tasks/<int:task_id>/move")
def manage_move_task(task_id: int):
    def run():
        parent_id = request.form.get("parent_id", type=int)
        if parent_id:  # under another task: it also takes that task's group
            services().manage.set_parent(task_id, parent_id)
        else:
            services().manage.set_parent(task_id, None)
            services().manage.set_group(task_id, request.form.get("group_id", type=int))
    return _manage_action(run)


# --- focus API (the browser extension) ---------------------------------------------

@bp.get("/focus")
def focus_page():
    return render_template("focus.html", focus=services().focus.status())


@bp.get("/api/focus")
def focus_status():
    return jsonify(services().focus.status())


@bp.post("/api/focus/history")
def focus_history():
    sites = (request.get_json(silent=True) or {}).get("sites")
    return jsonify(services().focus.judge_history(sites if isinstance(sites, list) else []))


@bp.post("/api/focus/check")
def focus_check():
    body = request.get_json(silent=True) or {}
    return jsonify(services().focus.check(body.get("domain"), body.get("title") or ""))


@bp.post("/api/focus/allow")
def focus_allow():
    return jsonify(services().focus.allow((request.get_json(silent=True) or {}).get("domain")))


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
        if task.status == TaskStatus.PAUSED:
            ctx["left_seconds"] = max(0, int((deadline_of(task) - task.paused_at).total_seconds()))
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
