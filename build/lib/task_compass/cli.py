"""Run an interview in the terminal, without the browser:

    python -m task_compass.cli "לסדר את המחסן"

Uses the real model (needs ANTHROPIC_API_KEY in .env) and the real database.
"""

import sys

from task_compass import texts_he
from task_compass.db import make_session_factory, session_scope
from task_compass.interview.service import InterviewService, is_pending, open_turn
from task_compass.llm.anthropic_client import AnthropicClient
from task_compass.llm.gateway import Gateway, LLMError
from task_compass.models import Task, TaskStatus


def print_card(task: Task) -> None:
    print("\n--- " + texts_he.CARD_TITLE + " ---")
    values = {
        "type": task.category.name_he if task.category else "",
        "deliverable": task.deliverable or "",
        "done_tests": "; ".join(task.done_tests or []),
        "boundaries": "; ".join(task.boundaries or []),
        "first_step": task.first_step or "",
    }
    for name, label in texts_he.FIELD_LABELS.items():
        verdict = (task.verdicts or {}).get(name, {})
        mark = texts_he.MARKS.get(verdict.get("status", "unchecked"))
        reason = f"  ({verdict['reason']})" if verdict.get("reason") else ""
        print(f"{mark} {label}: {values[name]}{reason}")
    print()


def main() -> None:
    factory = make_session_factory()
    service = InterviewService(Gateway(AnthropicClient(), factory), factory)
    opening = " ".join(sys.argv[1:]) or input(texts_he.CLI_OPENING_PROMPT)

    try:
        task_id = service.start(opening)
    except LLMError as exc:
        print(exc.message_he)
        return

    while True:
        with session_scope(factory) as session:
            task = session.get(Task, task_id)
            print_card(task)
            if task.status == TaskStatus.ESTIMATE:
                print(texts_he.CARD_READY)
                return
            if task.status == TaskStatus.STUCK:
                print(texts_he.STUCK_EXPLAIN)
                return
            pending = is_pending(task)
            turn = open_turn(task)
            if turn:
                if turn.note:
                    print(turn.note)
                print(f"[{turn.round_no}] {turn.question}")
                print(f"   ({texts_he.SAMPLE_LABEL} {turn.sample_answer})")
        try:
            if pending:
                input(texts_he.CLI_RETRY_PROMPT)
                service.retry(task_id)
            else:
                service.answer(task_id, input("> "))
        except LLMError as exc:
            print(exc.message_he)
        except (KeyboardInterrupt, EOFError):
            print()
            return


if __name__ == "__main__":
    main()
