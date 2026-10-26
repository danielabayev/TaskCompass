"""Estimate rules: the 2x gap and the corrected estimate."""

CLARIFICATION_GAP = 2.0
# Upper bound for any minutes value (30 days). Larger is a typo, and would not
# fit the database column.
MAX_MINUTES = 60 * 24 * 30


def needs_clarification(blind_min: int, model_min: int) -> bool:
    """A gap of 2x or more, in either direction, triggers a clarification round."""
    low, high = sorted((blind_min, model_min))
    return high >= CLARIFICATION_GAP * low


def corrected_estimate(blind_min: int, factor: float) -> int:
    """Blind estimate times the personal correction, in whole minutes."""
    return max(1, round(blind_min * factor))


def parse_minutes(raw: str | int | None) -> int | None:
    """A whole number of minutes between 1 and MAX_MINUTES, or None."""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if 0 < value <= MAX_MINUTES else None
