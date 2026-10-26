import pytest

from task_compass.domain.estimates import needs_clarification, parse_minutes


@pytest.mark.parametrize(
    "blind, model, expected",
    [(30, 70, True), (30, 50, False), (30, 60, True), (70, 30, True), (50, 30, False)],
)
def test_two_x_gap(blind, model, expected):
    assert needs_clarification(blind, model) is expected


@pytest.mark.parametrize("raw, expected", [("45", 45), (" 7 ", 7), ("0", None), ("-3", None), ("abc", None), (None, None), ("1.5", None), ("43200", 43200), ("43201", None), ("99999999999999", None)])
def test_parse_minutes(raw, expected):
    assert parse_minutes(raw) == expected
