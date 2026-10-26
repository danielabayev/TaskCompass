"""Estimate rules: the 2x gap and the corrected estimate."""

CLARIFICATION_GAP = 2.0


def needs_clarification(blind_min: int, model_min: int) -> bool:
    """A gap of 2x or more, in either direction, triggers a clarification round."""
    low, high = sorted((blind_min, model_min))
    return high >= CLARIFICATION_GAP * low


def corrected_estimate(blind_min: int, factor: float) -> int:
    """Blind estimate times the personal correction, in whole minutes."""
    return max(1, round(blind_min * factor))


def parse_minutes(raw: str | int | None) -> int | None:
    """A positive whole number of minutes, or None if the input is not one."""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None
