"""Execution rules: the timer, the checkpoint and the one-extension limit."""

import math
from datetime import datetime, timedelta

EXTEND, SPLIT, REDUCE, STOP = "extend", "split", "reduce", "stop"
CHOICES = (EXTEND, SPLIT, REDUCE, STOP)


class ExtensionNotAllowed(Exception):
    """A task gets one extension only."""


def deadline(started_at: datetime, binding_min: int, extension_min: int = 0) -> datetime:
    return started_at + timedelta(minutes=binding_min + extension_min)


def is_overdue(now: datetime, started_at: datetime, binding_min: int, extension_min: int) -> bool:
    return now >= deadline(started_at, binding_min, extension_min)


def elapsed_minutes(started_at: datetime, now: datetime) -> int:
    """Whole minutes, rounded up, at least 1."""
    return max(1, math.ceil((now - started_at).total_seconds() / 60))


def allowed_choices(previous_choices: list[str]) -> tuple[str, ...]:
    """After one extension only split, reduce and stop remain."""
    if EXTEND in previous_choices:
        return tuple(c for c in CHOICES if c != EXTEND)
    return CHOICES


def check_choice(choice: str, previous_choices: list[str]) -> None:
    if choice not in CHOICES:
        raise ValueError(f"unknown checkpoint choice {choice}")
    if choice not in allowed_choices(previous_choices):
        raise ExtensionNotAllowed()
