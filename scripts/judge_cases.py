"""Real-model checks for the card judge on answers it once got wrong.

    uv run python -m scripts.judge_cases                 # 3 runs on the judge model
    uv run python -m scripts.judge_cases --model claude-opus-5-5 --runs 5

Each case is a real interview step: the card before it, the question, the
person's answer, and what the card must (not) contain afterwards. It costs
real money (well under a cent per Haiku run) and writes only to llm_calls in
the test database.
"""

import argparse
from dataclasses import dataclass

from alembic import command
from alembic.config import Config

from task_compass import config
from task_compass.db import make_session_factory
from task_compass.llm.anthropic_client import AnthropicClient
from task_compass.llm.gateway import Gateway


@dataclass
class Case:
    name: str
    card: dict
    question: str
    answer: str
    boundaries_must: list[str]  # a word that must appear in some boundary
    boundaries_must_not: list[str]  # a word that must not appear in any boundary


CASES = [
    Case(
        # Task 1 on Daniel's PC, round 5 (2026-11-01): the question listed three
        # options, the answer kept only one out, the card took all three.
        name="options in the question are not answers",
        card={
            "type_key": "build",
            "deliverable": "תוסף לדפדפן במחשב שחוסם כניסה לאתרים שלא מועילים למשימה",
            "done_tests": [
                "בעת כניסה לאתר קשור למשימה, האתר נטען כרגיל ללא חסימה?",
                "בעת כניסה לאתר לא קשור למשימה, מופיע פופאפ שמודיע שהאתר חסום?",
            ],
            "boundaries": [],
            "first_step": None,
        },
        question="מה אתה משאיר בחוץ בגרסה הראשונה של התוסף: האפליקציה לפלאפון, "
                 "הסריקה מראש של היסטוריית הדפדפן, אפשרות לעקוף חסימה, או משהו אחר?",
        answer="את האפליקציה לפלאפון אני משאיר בחוץ בהתחלה\n"
               "את הסריקה של הדפדפן וההיסטוריה שלו ואת האפשרות לעקוף את החסימה נעשה בגרסה הזו",
        boundaries_must=["פלאפון"],
        boundaries_must_not=["היסטוריה", "היסטוריית", "לעקוף"],
    ),
]
# The same step when an earlier judge call had already put the three options
# on the card: the answer must take two of them out again.
CASES.append(Case(
    name="an answer can move a boundary back into scope",
    card={**CASES[0].card, "boundaries": [
        "אפליקציה לפלאפון", "סריקה מראש של היסטוריית הדפדפן", "אפשרות לעקוף את החסימה"]},
    question=CASES[0].question,
    answer=CASES[0].answer,
    boundaries_must=CASES[0].boundaries_must,
    boundaries_must_not=CASES[0].boundaries_must_not,
))


def check(case: Case, boundaries: list[str]) -> list[str]:
    text = " | ".join(boundaries)
    problems = [f"missing '{w}'" for w in case.boundaries_must if w not in text]
    problems += [f"should not contain '{w}'" for w in case.boundaries_must_not if w in text]
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=config.SMALL_MODEL)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    config.SMALL_MODEL = args.model  # the judge reads it at call time

    url = config.database_url(test=True)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    factory = make_session_factory(url)
    gateway = Gateway(AnthropicClient(), factory)
    active = {"build": "בנייה"}
    failed = 0
    for case in CASES:
        for run in range(1, args.runs + 1):
            result = gateway.judge(task_id=None, card=case.card, active_types=active,
                                   question=case.question, answer=case.answer)
            boundaries = list(result.boundaries)
            problems = check(case, boundaries)
            failed += bool(problems)
            print(f"[{'PASS' if not problems else 'FAIL'}] {case.name} (run {run}, {args.model}): "
                  f"{boundaries} {'; '.join(problems)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
