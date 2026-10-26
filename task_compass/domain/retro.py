"""When the retrospective is short and when it is deep."""

from task_compass import config

ON, OVER, UNDER = "on", "over", "under"
SHORT, DEEP = "short", "deep"


def deviation_ratio(actual_min: int, binding_min: int) -> float:
    return round(actual_min / binding_min, 3)


def direction(ratio: float) -> str:
    if ratio > config.ON_ESTIMATE_HIGH:
        return OVER
    if ratio < config.ON_ESTIMATE_LOW:
        return UNDER
    return ON


def retro_kind(ratio: float, unusual_event: bool) -> str:
    """Close to the estimate and nothing unusual: short (no questions).
    Over, under, or any unusual event (checkpoint, split, reduction, stop,
    clarification round): deep."""
    return DEEP if unusual_event or direction(ratio) != ON else SHORT


def hindsight_actual(actual_min: int, hindsight_min: int) -> int:
    """The time stated in hindsight replaces the actual time. It must be
    shorter than the measured time, otherwise it is not "shortened"."""
    if not 0 < hindsight_min < actual_min:
        raise ValueError("hindsight time must be positive and below the measured time")
    return hindsight_min
