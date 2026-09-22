"""T004 and T032: the invariants that make verification safe.

FR-025 says no number of check answers may move where the display reaches 0 %
or 100 %. That is guaranteed by the shape of the curve rather than by a clamp,
and this file is what holds it to that.

The curve family changed once, and the reason is worth keeping: the first one
was antisymmetric about the midpoint, so it passed through exactly (0.5, 0.5)
for every parameter. Since the check drives to the midpoint and asks how it
looks, it would never have had anything to see.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from somfy_shutters.calibration import (
    CURVE_MAX,
    CURVE_MIN,
    CURVE_NEUTRAL,
    CURVE_STEP,
    at_curve_limit,
    clamp_curve,
    curve_from_answers,
    midpoint_shift,
    travel_curve,
)
from somfy_shutters.models import CheckAnswer, CheckReply, Direction

BAND = [CURVE_MIN + i * 0.01 for i in range(int((CURVE_MAX - CURVE_MIN) * 100) + 1)]


@pytest.mark.parametrize("a", BAND)
def test_end_points_are_exact(a: float) -> None:
    assert travel_curve(0.0, a) == 0.0
    assert travel_curve(1.0, a) == 1.0


@pytest.mark.parametrize("a", BAND)
def test_curve_is_monotonic(a: float) -> None:
    """A display that runs backwards mid-travel would be worse than a wrong one."""
    steps = [travel_curve(i / 500, a) for i in range(501)]
    assert all(x <= y + 1e-12 for x, y in pairwise(steps))


def test_neutral_is_the_linear_behaviour_of_feature_001() -> None:
    for i in range(101):
        p = i / 100
        assert travel_curve(p, CURVE_NEUTRAL) == pytest.approx(p)


def test_the_midpoint_actually_moves() -> None:
    """The property the previous curve family lacked, which made the check useless."""
    assert midpoint_shift(CURVE_NEUTRAL) == pytest.approx(0.0)
    assert abs(midpoint_shift(CURVE_NEUTRAL + CURVE_STEP)) > 1.0
    assert abs(midpoint_shift(CURVE_NEUTRAL - CURVE_STEP)) > 1.0


def test_one_answer_shifts_the_middle_by_about_1_7_points() -> None:
    assert abs(midpoint_shift(CURVE_NEUTRAL + CURVE_STEP)) == pytest.approx(1.7, abs=0.1)


def test_the_bounds_cap_the_whole_control() -> None:
    assert midpoint_shift(CURVE_MIN) == pytest.approx(11.6, abs=0.2)
    assert midpoint_shift(CURVE_MAX) == pytest.approx(-12.1, abs=0.2)


def test_clamping() -> None:
    assert clamp_curve(5.0) == CURVE_MAX
    assert clamp_curve(0.1) == CURVE_MIN
    assert at_curve_limit(CURVE_MAX) is True
    assert at_curve_limit(CURVE_MIN) is True
    assert at_curve_limit(CURVE_NEUTRAL) is False


def answers(*replies: CheckReply) -> list[CheckAnswer]:
    return [CheckAnswer(shutter_id="wohnzimmer", direction=Direction.UP, answer=r) for r in replies]


def test_answers_describe_the_shutter_not_the_display() -> None:
    """ "Zu hoch" means the shutter hangs higher than the halfway mark the display
    claims, so the display has to show more at that point in the travel."""
    higher = curve_from_answers(answers(CheckReply.TOO_HIGH))
    assert higher < CURVE_NEUTRAL
    assert travel_curve(0.5, higher) > 0.5, "the display has to catch up upwards"

    lower = curve_from_answers(answers(CheckReply.TOO_LOW))
    assert lower > CURVE_NEUTRAL
    assert travel_curve(0.5, lower) < 0.5

    assert curve_from_answers(answers(CheckReply.ABOUT_RIGHT)) == CURVE_NEUTRAL


def test_answers_cannot_escape_the_bounds() -> None:
    a = curve_from_answers(answers(*([CheckReply.TOO_HIGH] * 40)))
    assert a == CURVE_MIN
    assert travel_curve(0.0, a) == 0.0
    assert travel_curve(1.0, a) == 1.0


def test_end_points_survive_any_sequence_of_answers() -> None:
    """The property FR-025 actually asks for, over arbitrary histories."""
    import random

    rng = random.Random(20260922)
    for _ in range(200):
        seq = rng.choices(list(CheckReply), k=rng.randint(0, 25))
        a = curve_from_answers(answers(*seq))
        assert travel_curve(0.0, a) == 0.0
        assert travel_curve(1.0, a) == 1.0
        assert CURVE_MIN <= a <= CURVE_MAX
