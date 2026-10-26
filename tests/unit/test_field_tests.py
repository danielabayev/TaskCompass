from task_compass.domain.field_tests import FAIL, PASS, UNCHECKED, Card, combine
from task_compass.domain.readiness import is_ready, missing_fields, weakest_field

ACTIVE = {"build", "fix", "learn", "write", "decide", "errands"}
ALL_PASS = {f: {"status": PASS, "reason": ""} for f in ("deliverable", "done_tests", "boundaries", "first_step")}


def full_card(**overrides) -> Card:
    card = Card(
        type_key="write",
        deliverable="מייל שנשלח למנהל",
        done_tests=["המייל נשלח?"],
        boundaries=["לא כולל פגישה"],
        first_step="לפתוח טיוטה חדשה",
    )
    for key, value in overrides.items():
        setattr(card, key, value)
    return card


def test_all_fields_pass_makes_card_ready():
    verdicts = combine(full_card(), ACTIVE, ALL_PASS)
    assert is_ready(verdicts)
    assert weakest_field(verdicts) is None


def test_inactive_or_missing_type_fails_in_code():
    assert combine(full_card(type_key="other"), ACTIVE, ALL_PASS)["type"]["status"] == FAIL
    assert combine(full_card(type_key=None), ACTIVE, ALL_PASS)["type"]["status"] == FAIL


def test_done_tests_must_number_one_to_five():
    assert combine(full_card(done_tests=[]), ACTIVE, ALL_PASS)["done_tests"]["status"] == FAIL
    six = [f"בדיקה {i}?" for i in range(6)]
    assert combine(full_card(done_tests=six), ACTIVE, ALL_PASS)["done_tests"]["status"] == FAIL
    five = six[:5]
    assert combine(full_card(done_tests=five), ACTIVE, ALL_PASS)["done_tests"]["status"] == PASS


def test_blank_strings_do_not_count():
    verdicts = combine(full_card(boundaries=["  "], done_tests=[""]), ACTIVE, ALL_PASS)
    assert verdicts["boundaries"]["status"] == FAIL
    assert verdicts["done_tests"]["status"] == FAIL


def test_code_overrides_a_model_pass_but_model_can_fail_a_code_pass():
    verdicts = combine(full_card(boundaries=[]), ACTIVE, ALL_PASS)
    assert verdicts["boundaries"]["status"] == FAIL
    model = dict(ALL_PASS, deliverable={"status": FAIL, "reason": "זו פעילות"})
    verdicts = combine(full_card(), ACTIVE, model)
    assert verdicts["deliverable"] == {"status": FAIL, "reason": "זו פעילות"}


def test_unjudged_field_is_unchecked_and_not_ready():
    verdicts = combine(full_card(), ACTIVE, {})
    assert verdicts["deliverable"]["status"] == UNCHECKED
    assert not is_ready(verdicts)


def test_no_move_to_estimation_while_a_test_fails():
    model = dict(ALL_PASS, first_step={"status": FAIL, "reason": "לא צעד יחיד"})
    verdicts = combine(full_card(), ACTIVE, model)
    assert not is_ready(verdicts)
    assert missing_fields(verdicts) == ["first_step"]


def test_weakest_field_follows_card_order():
    model = dict(ALL_PASS, first_step={"status": FAIL, "reason": "x"})
    verdicts = combine(full_card(deliverable=""), ACTIVE, model)
    assert weakest_field(verdicts) == "deliverable"
