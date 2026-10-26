""""Ready for estimation?" and "which field to ask about next?"."""

from task_compass.domain.field_tests import FIELDS, PASS


def is_ready(verdicts: dict[str, dict]) -> bool:
    """True only when every card field passed its test."""
    return all(verdicts.get(name, {}).get("status") == PASS for name in FIELDS)


def missing_fields(verdicts: dict[str, dict]) -> list[str]:
    """Fields that did not pass, in interview order."""
    return [name for name in FIELDS if verdicts.get(name, {}).get("status") != PASS]


def weakest_field(verdicts: dict[str, dict]) -> str | None:
    """The field the next question targets: the first one that has not passed,
    in card order. Card order matters because later fields depend on earlier
    ones (done tests depend on the deliverable, and so on)."""
    missing = missing_fields(verdicts)
    return missing[0] if missing else None
