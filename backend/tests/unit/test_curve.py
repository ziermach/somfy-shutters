"""T004 and T032: the invariants that make verification safe.

FR-025 says no number of check answers may move where the display reaches 0 %
or 100 %. That is guaranteed by the shape of the curve rather than by a clamp,
and this file is what holds it to that.
"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from somfy_shutters.calibration import (
    CURVE_BOUND,
    CURVE_STEP,
    at_curve_limit,
    clamp_curve,
    curve_from_answers,
    travel_curve,
)
from somfy_shutters.models import CheckAnswer, CheckReply, Direction

BAND = [i / 100 for i in range(-80, 81)]


@pytest.mark.parametrize("k", BAND)
def test_end_points_are_exact(k: float) -> None:
    assert travel_curve(0.0, k) == pytest.approx(0.0, abs=1e-12)
    assert travel_curve(1.0, k) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("k", BAND)
def test_curve_is_monotonic(k: float) -> None:
    """A display that runs backwards mid-travel would be worse than a wrong one."""
    steps = [travel_curve(i / 500, k) for i in range(501)]
    assert all(a <= b + 1e-12 for a, b in pairwise(steps))


def test_zero_is_the_linear_behaviour_of_feature_001() -> None:
    for i in range(101):
        p = i / 100
        assert travel_curve(p, 0.0) == pytest.approx(p)


def test_one_answer_shifts_mid_travel_by_about_1_6_points() -> None:
    shift = abs(travel_curve(0.25, CURVE_STEP) - 0.25) * 100
    assert shift == pytest.approx(CURVE_STEP / (2 * math.pi) * 100, abs=0.01)
    assert 1.5 < shift < 1.7


def test_the_bound_caps_the_whole_control() -> None:
    worst = max(abs(travel_curve(i / 1000, CURVE_BOUND) - i / 1000) for i in range(1001))
    assert worst * 100 == pytest.approx(12.7, abs=0.1)


def test_clamping() -> None:
    assert clamp_curve(5.0) == CURVE_BOUND
    assert clamp_curve(-5.0) == -CURVE_BOUND
    assert at_curve_limit(CURVE_BOUND) is True
    assert at_curve_limit(0.3) is False


def answers(*replies: CheckReply) -> list[CheckAnswer]:
    return [CheckAnswer(shutter_id="wohnzimmer", direction=Direction.UP, answer=r) for r in replies]


def test_answers_accumulate_in_the_right_direction() -> None:
    assert curve_from_answers(answers(CheckReply.TOO_HIGH)) == pytest.approx(-CURVE_STEP)
    assert curve_from_answers(answers(CheckReply.TOO_LOW)) == pytest.approx(CURVE_STEP)
    assert curve_from_answers(answers(CheckReply.ABOUT_RIGHT)) == 0.0


def test_answers_cannot_escape_the_bound() -> None:
    k = curve_from_answers(answers(*([CheckReply.TOO_LOW] * 40)))
    assert k == CURVE_BOUND
    assert travel_curve(0.0, k) == pytest.approx(0.0, abs=1e-12)
    assert travel_curve(1.0, k) == pytest.approx(1.0, abs=1e-12)


def test_end_points_survive_any_sequence_of_answers() -> None:
    """The property FR-025 actually asks for, over arbitrary histories."""
    import random

    rng = random.Random(20260921)
    for _ in range(200):
        seq = rng.choices(list(CheckReply), k=rng.randint(0, 25))
        k = curve_from_answers(answers(*seq))
        assert travel_curve(0.0, k) == pytest.approx(0.0, abs=1e-12)
        assert travel_curve(1.0, k) == pytest.approx(1.0, abs=1e-12)
