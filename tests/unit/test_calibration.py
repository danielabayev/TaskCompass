from task_compass.domain.calibration import SOURCE_GLOBAL, SOURCE_NONE, SOURCE_TYPE, Sample, factor_for
from task_compass.domain.estimates import corrected_estimate


def s(type_key, blind, actual):
    return Sample(type_key, blind, actual)


def test_median_example_from_the_spec():
    samples = [s("build", 10, 15), s("build", 10, 20), s("build", 10, 12)]  # 1.5, 2.0, 1.2
    cal = factor_for("build", samples)
    assert cal.factor == 1.5 and cal.source == SOURCE_TYPE
    assert corrected_estimate(60, cal.factor) == 90


def test_falls_back_to_global_when_type_has_fewer_than_three():
    samples = [s("build", 10, 20), s("learn", 10, 10), s("write", 10, 30)]
    cal = factor_for("build", samples)
    assert cal.source == SOURCE_GLOBAL and cal.factor == 2.0


def test_no_history_gives_one():
    cal = factor_for("build", [s("build", 10, 20)])
    assert cal == type(cal)(1.0, SOURCE_NONE)


def test_window_uses_most_recent_only():
    recent = [s("fix", 10, 10)] * 3
    old = [s("fix", 10, 50)] * 10
    assert factor_for("fix", recent + old, window=3).factor == 1.0


def test_zero_values_are_ignored():
    samples = [s("fix", 0, 10), s("fix", 10, 0), s("fix", 10, 20)]
    assert factor_for("fix", samples).source == SOURCE_NONE
