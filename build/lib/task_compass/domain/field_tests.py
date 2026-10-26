"""The test for each field of the task card (decisions doc, section 5).

A field passes only if its code test passes AND, for fields that need
judgment, the model's verdict is "pass". The code always has the last word:
the model can fail a field the code accepts, never the reverse.
"""

from dataclasses import dataclass, field

from task_compass import texts_he

# Card fields in the order the interview works through them.
FIELDS = ("type", "deliverable", "done_tests", "boundaries", "first_step")

# Fields whose quality needs judgment (an activity vs. a pointable result, a
# yes/no test, a concrete boundary, a 5-minute first step).
MODEL_JUDGED = ("deliverable", "done_tests", "boundaries", "first_step")

PASS, FAIL, UNCHECKED = "pass", "fail", "unchecked"

MAX_DONE_TESTS = 5


@dataclass
class Card:
    type_key: str | None = None
    deliverable: str | None = None
    done_tests: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    first_step: str | None = None


def _filled(text: str | None) -> bool:
    return bool(text and text.strip())


def code_check(name: str, card: Card, active_types: set[str]) -> str | None:
    """Return None if the code test passes, else a Hebrew reason."""
    if name == "type":
        return None if card.type_key in active_types else texts_he.REASON_TYPE_MISSING
    if name == "deliverable":
        return None if _filled(card.deliverable) else texts_he.REASON_EMPTY
    if name == "done_tests":
        tests = [t for t in card.done_tests if _filled(t)]
        if not tests:
            return texts_he.REASON_EMPTY
        if len(tests) > MAX_DONE_TESTS:
            return texts_he.REASON_TOO_MANY_TESTS
        return None
    if name == "boundaries":
        return None if any(_filled(b) for b in card.boundaries) else texts_he.REASON_NO_BOUNDARY
    if name == "first_step":
        return None if _filled(card.first_step) else texts_he.REASON_EMPTY
    raise ValueError(f"unknown field {name}")


def combine(card: Card, active_types: set[str], model_verdicts: dict[str, dict]) -> dict[str, dict]:
    """Final verdict per field: {"status": pass|fail|unchecked, "reason": str}.

    `model_verdicts` holds the model's judgment for MODEL_JUDGED fields. A
    field the model did not judge stays "unchecked" (which is not a pass).
    """
    result: dict[str, dict] = {}
    for name in FIELDS:
        reason = code_check(name, card, active_types)
        if reason:
            result[name] = {"status": FAIL, "reason": reason}
        elif name not in MODEL_JUDGED:
            result[name] = {"status": PASS, "reason": ""}
        else:
            verdict = model_verdicts.get(name)
            if verdict is None:
                result[name] = {"status": UNCHECKED, "reason": ""}
            else:
                result[name] = {"status": verdict["status"], "reason": verdict.get("reason", "")}
    return result
