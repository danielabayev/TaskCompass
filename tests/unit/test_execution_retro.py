from datetime import datetime, timedelta, timezone

import pytest

from task_compass.domain import execution, retro

T0 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)


def test_deadline_includes_extension():
    assert execution.deadline(T0, 30, 10) == T0 + timedelta(minutes=40)
    assert execution.is_overdue(T0 + timedelta(minutes=30), T0, 30, 0)
    assert not execution.is_overdue(T0 + timedelta(minutes=29), T0, 30, 0)


def test_elapsed_rounds_up_and_is_at_least_one():
    assert execution.elapsed_minutes(T0, T0 + timedelta(seconds=10)) == 1
    assert execution.elapsed_minutes(T0, T0 + timedelta(minutes=30, seconds=1)) == 31


def test_second_extension_is_rejected():
    execution.check_choice("extend", [])
    with pytest.raises(execution.ExtensionNotAllowed):
        execution.check_choice("extend", ["extend"])
    assert execution.allowed_choices(["extend"]) == ("split", "reduce", "stop")
    execution.check_choice("stop", ["extend"])


def test_unknown_choice_is_an_error():
    with pytest.raises(ValueError):
        execution.check_choice("pause", [])


@pytest.mark.parametrize(
    "actual, binding, unusual, kind, direction",
    [
        (60, 60, False, "short", "on"),
        (70, 60, False, "short", "on"),  # 1.17
        (80, 60, False, "deep", "over"),  # 1.33
        (40, 60, False, "deep", "under"),  # 0.67
        (60, 60, True, "deep", "on"),  # unusual event forces deep
    ],
)
def test_retro_kind(actual, binding, unusual, kind, direction):
    ratio = retro.deviation_ratio(actual, binding)
    assert retro.direction(ratio) == direction
    assert retro.retro_kind(ratio, unusual) == kind


def test_hindsight_must_be_shorter_than_measured():
    assert retro.hindsight_actual(60, 30) == 30
    for bad in (0, 60, 90):
        with pytest.raises(ValueError):
            retro.hindsight_actual(60, bad)
