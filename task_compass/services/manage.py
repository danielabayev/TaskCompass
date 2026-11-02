"""Managing tasks: delete them, put one under another, bundle them in groups.

A sub-task always sits in its parent's group: moving a task into a group moves
its sub-tasks too, and putting a task under another gives it that group.
Deleting a task moves its sub-tasks up one level; they are not deleted.
"""

from dataclasses import dataclass, field

from sqlalchemy import delete, select, update
from sqlalchemy.orm import sessionmaker

from task_compass import config, texts_he
from task_compass.db import session_scope
from task_compass.errors import FlowError
from task_compass.models import (
    Checkpoint, InterviewTurn, LlmCall, Retro, SiteVerdict, Task, TaskGroup,
)
from task_compass.services.common import get_task


@dataclass
class Node:
    task: Task
    children: list["Node"] = field(default_factory=list)


@dataclass
class Section:
    group: TaskGroup | None  # None = tasks that are in no group
    nodes: list[Node]


def _descendants(session, task_id: int) -> list[Task]:
    found, frontier = [], [task_id]
    while frontier:
        kids = session.scalars(select(Task).where(Task.parent_id.in_(frontier))).all()
        found.extend(kids)
        frontier = [k.id for k in kids]
    return found


def _group(session, group_id: int | None) -> TaskGroup | None:
    if group_id is None:
        return None
    group = session.get(TaskGroup, group_id)
    if group is None:
        raise FlowError(texts_he.ERROR_NO_GROUP)
    return group


class ManageService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def tree(self) -> list[Section]:
        """Groups first, then the ungrouped tasks; inside each, tasks nested by parent."""
        with session_scope(self.session_factory) as session:
            tasks = session.scalars(select(Task).where(Task.user_id == config.USER_ID).order_by(Task.id)).all()
            groups = session.scalars(select(TaskGroup).order_by(TaskGroup.id)).all()
            nodes = {t.id: Node(t) for t in tasks}
            roots: dict[int | None, list[Node]] = {}
            for t in tasks:
                parent = nodes.get(t.parent_id)
                if parent is not None and parent.task.group_id == t.group_id:
                    parent.children.append(nodes[t.id])
                else:
                    roots.setdefault(t.group_id, []).append(nodes[t.id])
            sections = [Section(g, roots.get(g.id, [])) for g in groups]
            sections.append(Section(None, roots.get(None, [])))
            return sections

    def groups(self) -> list[TaskGroup]:
        with session_scope(self.session_factory) as session:
            return session.scalars(select(TaskGroup).order_by(TaskGroup.id)).all()

    def delete_task(self, task_id: int) -> None:
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id)
            session.execute(update(Task).where(Task.parent_id == task_id).values(parent_id=task.parent_id))
            session.execute(update(LlmCall).where(LlmCall.task_id == task_id).values(task_id=None))  # keeps the spend history
            for table in (SiteVerdict, Checkpoint, Retro, InterviewTurn):
                session.execute(delete(table).where(table.task_id == task_id))
            session.delete(task)

    def set_parent(self, task_id: int, parent_id: int | None) -> None:
        """Put a task under another (or back at the top level with None)."""
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id)
            if parent_id is None:
                task.parent_id = None
                return
            if parent_id == task_id:
                raise FlowError(texts_he.ERROR_PARENT_SELF)
            parent = get_task(session, parent_id)
            if parent.id in {t.id for t in _descendants(session, task_id)}:
                raise FlowError(texts_he.ERROR_PARENT_CYCLE)
            task.parent_id = parent.id
            for t in [task, *_descendants(session, task_id)]:
                t.group_id = parent.group_id

    def set_group(self, task_id: int, group_id: int | None) -> None:
        """Move a task, with all its sub-tasks, into a group (None = out of any group)."""
        with session_scope(self.session_factory) as session:
            task = get_task(session, task_id)
            _group(session, group_id)
            for t in [task, *_descendants(session, task_id)]:
                t.group_id = group_id
            # A task moved away from its parent's group becomes a top-level task there.
            if task.parent_id is not None and session.get(Task, task.parent_id).group_id != group_id:
                task.parent_id = None

    def create_group(self, name: str) -> int:
        name = (name or "").strip()
        if not name:
            raise FlowError(texts_he.ERROR_GROUP_NAME)
        with session_scope(self.session_factory) as session:
            group = TaskGroup(name=name[:80])
            session.add(group)
            session.flush()
            return group.id

    def rename_group(self, group_id: int, name: str) -> None:
        name = (name or "").strip()
        if not name:
            raise FlowError(texts_he.ERROR_GROUP_NAME)
        with session_scope(self.session_factory) as session:
            _group(session, group_id).name = name[:80]

    def delete_group(self, group_id: int) -> None:
        """The tasks stay; they just leave the group."""
        with session_scope(self.session_factory) as session:
            _group(session, group_id)
            session.execute(update(Task).where(Task.group_id == group_id).values(group_id=None))
            session.execute(delete(TaskGroup).where(TaskGroup.id == group_id))
