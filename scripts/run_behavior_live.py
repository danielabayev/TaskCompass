"""Layer 2 with the real model: every test task 3 times, each must pass 3/3.

    python -m scripts.run_behavior_live            # all scenarios
    python -m scripts.run_behavior_live 1 4        # only scenarios 1 and 4
    python -m scripts.run_behavior_live --runs 1   # quick single run

Run it by hand after every prompt or model change. It costs real money (a few
cents per scenario run) and writes to the test database, never the real one.
"""

import argparse
import sys

from alembic import command
from alembic.config import Config

from task_compass import config
from task_compass.db import make_session_factory, session_scope
from task_compass.interview.service import InterviewService, open_turn
from task_compass.llm.anthropic_client import AnthropicClient
from task_compass.llm.gateway import Gateway, LLMError
from task_compass.models import Task, TaskStatus
from tests.behavior.scenarios import COMMON_CHECKS, SCENARIOS, Scenario


def snapshot(factory, task_id: int) -> dict:
    with session_scope(factory) as session:
        task = session.get(Task, task_id)
        turn = open_turn(task)
        answered = sum(1 for t in task.turns if t.answer is not None)
        return {
            "round": turn.round_no if turn else answered,
            "field": turn.field if turn else None,
            "question": turn.question if turn else None,
            "note": turn.note if turn else None,
            "status": task.status,
            "verdicts": dict(task.verdicts or {}),
            "type_key": task.category.key if task.category else None,
        }


def run_once(service: InterviewService, factory, scenario: Scenario) -> list[str]:
    trace = []
    task_id = service.start(scenario.opening)
    trace.append(snapshot(factory, task_id))
    for _ in range(scenario.max_answers):
        step = trace[-1]
        if step["status"] != TaskStatus.INTERVIEW:
            break
        if scenario.change_type_at and scenario.change_type_at[0] == step["round"]:
            service.change_type(task_id, scenario.change_type_at[1])
            step = snapshot(factory, task_id)
            trace.append(step)
        service.answer(task_id, scenario.answer(step["round"], step["field"]))
        trace.append(snapshot(factory, task_id))
    return [msg for check in COMMON_CHECKS + scenario.checks if (msg := check(trace))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*", type=int)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    url = config.database_url(test=True)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    factory = make_session_factory(url)
    service = InterviewService(Gateway(AnthropicClient(), factory), factory)

    failed = 0
    for scenario in SCENARIOS:
        if args.ids and scenario.id not in args.ids:
            continue
        passes = 0
        for run in range(1, args.runs + 1):
            try:
                problems = run_once(service, factory, scenario)
            except LLMError as exc:
                problems = [f"model error: {exc.message_he}"]
            passes += not problems
            label = "PASS" if not problems else "FAIL"
            print(f"[{scenario.id}] {scenario.name} run {run}: {label} {'; '.join(problems)}")
        ok = passes == args.runs
        failed += not ok
        print(f"[{scenario.id}] {passes}/{args.runs} {'OK' if ok else 'NOT OK'}{' (draft)' if scenario.draft else ''}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
