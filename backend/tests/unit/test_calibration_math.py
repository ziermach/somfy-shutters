"""T005: medians and rejection rules."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from somfy_shutters.calibration import (
    RETAIN_RUNS,
    RejectionReason,
    derive,
    rejection_for,
)
from somfy_shutters.models import Direction, MeasurementRun, RunKind

WHEN = datetime(2026, 9, 21, 18, 0, tzinfo=None).replace(tzinfo=__import__("datetime").timezone.utc)


def run(
    total: float, dead: float = 0.7, rejected: str | None = None, at: int = 0
) -> MeasurementRun:
    return MeasurementRun(
        shutter_id="wohnzimmer",
        direction=Direction.UP,
        dead_seconds=dead,
        total_seconds=total,
        recorded_at=WHEN + timedelta(minutes=at),
        kind=RunKind.GUIDED,
        rejected=rejected,
    )


# --- median, never mean ------------------------------------------------------


def test_three_runs_yield_the_middle_one() -> None:
    result = derive([run(18.0), run(21.0), run(18.4)], now=WHEN)
    assert result.travel_seconds == 18.4
    assert result.runs == 3


def test_one_late_press_does_not_drag_the_value() -> None:
    """The whole reason FR-013 says median: a mean would land at 19.1."""
    median_result = derive([run(18.0), run(18.2), run(21.0)], now=WHEN)
    assert median_result.travel_seconds == 18.2
    mean = (18.0 + 18.2 + 21.0) / 3
    assert abs(median_result.travel_seconds - mean) > 0.8


def test_rejected_runs_do_not_count_but_are_still_passed_in() -> None:
    result = derive(
        [run(18.0), run(2.0, rejected=RejectionReason.IMPLAUSIBLE), run(18.4)], now=WHEN
    )
    assert result.runs == 2
    assert result.travel_seconds == pytest.approx(18.2)


def test_no_valid_runs_derives_nothing() -> None:
    assert derive([], now=WHEN) is None
    assert derive([run(2.0, rejected=RejectionReason.TOO_SHORT)], now=WHEN) is None


def test_only_the_recent_runs_feed_the_median() -> None:
    """FR-021: a genuine change is followed; the window is bounded."""
    old = [run(18.0, at=i) for i in range(RETAIN_RUNS)]
    new = [run(25.0, at=RETAIN_RUNS + i) for i in range(RETAIN_RUNS)]
    assert derive(old + new, now=WHEN).travel_seconds == 25.0


def test_a_single_outlier_among_recent_runs_does_not_move_it() -> None:
    runs = [run(18.0, at=i) for i in range(6)] + [run(40.0, at=7)]
    assert derive(runs, now=WHEN).travel_seconds == 18.0


# --- rejection rules ---------------------------------------------------------


def test_dead_time_after_arrival() -> None:
    assert rejection_for(19.0, 18.0, None) == RejectionReason.DEAD_AFTER_ARRIVAL


def test_too_short() -> None:
    assert rejection_for(0.1, 0.5, None) == RejectionReason.TOO_SHORT


def test_implausible_against_an_established_value() -> None:
    assert rejection_for(0.7, 8.9, 18.0) == RejectionReason.IMPLAUSIBLE  # under half
    assert rejection_for(0.7, 37.0, 18.0) == RejectionReason.IMPLAUSIBLE  # over double
    # the band is inclusive at both ends
    assert rejection_for(0.7, 9.0, 18.0) is None
    assert rejection_for(0.7, 36.0, 18.0) is None


def test_nothing_is_implausible_before_a_value_exists() -> None:
    """The first run has nothing to be compared against, and must be kept."""
    assert rejection_for(0.7, 40.0, None) is None


def test_a_good_run_is_not_rejected() -> None:
    assert rejection_for(0.7, 18.2, 18.0) is None
