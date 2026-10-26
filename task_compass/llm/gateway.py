"""The single entry point to the language model.

The rest of the app calls Gateway.judge / ask / propose and gets validated
pydantic objects back, or an LLMError with a Hebrew message. The gateway:
- refuses to call the model once the month's spend reached the local cap,
- logs every call (model, tokens, cost, success) in llm_calls,
- gives an invalid answer one repair attempt, then fails.
The client underneath is swappable: AnthropicClient in the app, FakeClient in tests.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Protocol, TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from task_compass import config, texts_he
from task_compass.db import session_scope
from task_compass.llm.schemas import JudgeResult, Proposal, Question
from task_compass.models import LlmCall

T = TypeVar("T", bound=BaseModel)
PROMPTS_DIR = Path(__file__).parent / "prompts"


class InvalidAnswer(Exception):
    """The model's answer did not match the schema or a rule (worth one repair)."""


class CallFailed(Exception):
    """The call itself failed after the client's own retries (network, overload, ...)."""


class LLMError(Exception):
    """Final failure. `message_he` is shown to the user next to a retry button."""

    def __init__(self, message_he: str):
        super().__init__(message_he)
        self.message_he = message_he


@dataclass
class Completion:
    parsed: BaseModel
    input_tokens: int
    output_tokens: int


class LLMClient(Protocol):
    def complete(
        self, *, purpose: str, model: str, system: str, user: str, schema: type[T]
    ) -> Completion:
        """Return a parsed answer, or raise InvalidAnswer / CallFailed.
        Both exceptions may carry `input_tokens` / `output_tokens` attributes."""


def load_prompt(name: str) -> str:
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return text.replace("{{type_guidance}}", (PROMPTS_DIR / "types.md").read_text(encoding="utf-8"))


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    price_in, price_out = config.PRICES_PER_MTOK.get(model, (0.0, 0.0))
    usd = (input_tokens * price_in + output_tokens * price_out) / 1_000_000
    return Decimal(str(round(usd, 6)))


def month_spend(session, now: datetime | None = None) -> Decimal:
    now = now or datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = session.scalar(
        select(func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(
            LlmCall.user_id == config.USER_ID, LlmCall.created_at >= start
        )
    )
    return Decimal(total)


def count_questions(text: str) -> int:
    return text.count("?") + text.count("؟")


class Gateway:
    def __init__(self, client: LLMClient, session_factory: sessionmaker, settings: config.Settings | None = None):
        self.client = client
        self.session_factory = session_factory
        self.settings = settings or config.Settings()

    # --- the three calls the app makes -------------------------------------

    def judge(self, *, task_id: int | None, card: dict, active_types: dict[str, str],
              question: str | None, answer: str) -> JudgeResult:
        # Once a type is set, only the person changes it (in the interface).
        type_rule = (
            "It is already set; return it unchanged."
            if card.get("type_key")
            else "Suggest the best-fitting key from the active types."
        )
        system = load_prompt("judge").replace("{{type_rule}}", type_rule)
        user = _sections(
            ("Active task types (key: Hebrew name)", _json(active_types)),
            ("Current card", _json(card)),
            ("Question that was asked", question or "(none - this is the opening text of the task)"),
            ("The person's message", answer),
        )
        return self._call("judge", config.SMALL_MODEL, system, user, JudgeResult, task_id)

    def ask(self, *, task_id: int | None, card: dict, verdicts: dict, field: str,
            history: list[tuple[str, str]], lessons: list[str]) -> Question:
        user = _sections(
            ("Current card", _json(card)),
            ("Verdict per field", _json(verdicts)),
            ("Field to ask about now", field),
            ("Earlier questions and answers (oldest first)", _json(history) if history else "(none)"),
            ("Lessons from earlier tasks of this type", "\n".join(lessons) if lessons else "(none)"),
        )

        def one_question(q: Question) -> None:
            if not q.question.strip() or count_questions(q.question) > 1:
                raise InvalidAnswer("The question must be a single question with at most one question mark.")

        return self._call("ask", config.STRONG_MODEL, load_prompt("ask"), user, Question, task_id, one_question)

    def propose(self, *, task_id: int | None, card: dict, clarification: str | None) -> Proposal:
        user = _sections(
            ("Task card", _json(card)),
            ("Clarification from the person", clarification or "(none)"),
        )

        def sane(p: Proposal) -> None:
            if not p.subtasks or any(s.minutes <= 0 for s in p.subtasks):
                raise InvalidAnswer("Give at least one subtask, each with a positive number of minutes.")

        return self._call("propose", config.STRONG_MODEL, load_prompt("propose"), user, Proposal, task_id, sane)

    # --- shared machinery ---------------------------------------------------

    def _call(self, purpose: str, model: str, system: str, user: str, schema: type[T],
              task_id: int | None, validate: Callable[[T], None] | None = None) -> T:
        with session_scope(self.session_factory) as session:
            if month_spend(session) >= Decimal(str(self.settings.monthly_cost_cap_usd)):
                raise LLMError(texts_he.ERROR_COST_CAP)

        prompt = user
        for attempt in (1, 2):  # the second attempt is the single repair
            try:
                result = self.client.complete(purpose=purpose, model=model, system=system, user=prompt, schema=schema)
                if validate:
                    validate(result.parsed)
            except InvalidAnswer as exc:
                self._log(purpose, model, task_id, exc, success=False, error=f"invalid: {exc}"[:200])
                if attempt == 2:
                    raise LLMError(texts_he.ERROR_INVALID_ANSWER) from exc
                prompt = f"{user}\n\n# Your previous answer was rejected\n{exc}\nAnswer again, following the rules exactly."
                continue
            except CallFailed as exc:
                self._log(purpose, model, task_id, exc, success=False, error=str(exc)[:200])
                raise LLMError(texts_he.ERROR_CALL_FAILED) from exc
            self._log(purpose, model, task_id, result, success=True)
            return result.parsed
        raise AssertionError("unreachable")

    def _log(self, purpose, model, task_id, source, *, success: bool, error: str | None = None) -> None:
        """Written in its own transaction so the record survives a later rollback."""
        tokens_in = getattr(source, "input_tokens", 0) or 0
        tokens_out = getattr(source, "output_tokens", 0) or 0
        with session_scope(self.session_factory) as session:
            session.add(LlmCall(
                task_id=task_id, purpose=purpose, model=model,
                input_tokens=tokens_in, output_tokens=tokens_out,
                cost_usd=cost_usd(model, tokens_in, tokens_out),
                success=success, error=error,
            ))


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1)


def _sections(*parts: tuple[str, str]) -> str:
    return "\n\n".join(f"# {title}\n{body}" for title, body in parts)
