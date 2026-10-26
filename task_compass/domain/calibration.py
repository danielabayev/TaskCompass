"""The personal correction factor ("calibration factor" in the spec).

factor = median(actual / blind estimate) over the most recent finished tasks.
Always compared with the raw blind estimate, never with the binding one, so
the factor does not oscillate.

Fallback rule: the type's own factor (at least N samples), otherwise the
global factor (at least N samples), otherwise 1 with "no history yet".
"""

from dataclasses import dataclass
from statistics import median

from task_compass import config

SOURCE_TYPE, SOURCE_GLOBAL, SOURCE_NONE = "type", "global", "none"


@dataclass(frozen=True)
class Sample:
    """One finished task. Pass samples newest first."""

    type_key: str
    blind_min: int
    actual_min: int


@dataclass(frozen=True)
class Calibration:
    factor: float
    source: str  # type | global | none


def _factor(samples: list[Sample], window: int) -> float:
    recent = samples[:window]
    return median(s.actual_min / s.blind_min for s in recent)


def factor_for(
    type_key: str,
    samples: list[Sample],
    window: int = config.CALIBRATION_WINDOW,
    min_samples: int = config.CALIBRATION_MIN_SAMPLES,
) -> Calibration:
    usable = [s for s in samples if s.blind_min > 0 and s.actual_min > 0]
    own = [s for s in usable if s.type_key == type_key]
    if len(own) >= min_samples:
        return Calibration(round(_factor(own, window), 3), SOURCE_TYPE)
    if len(usable) >= min_samples:
        return Calibration(round(_factor(usable, window), 3), SOURCE_GLOBAL)
    return Calibration(1.0, SOURCE_NONE)
