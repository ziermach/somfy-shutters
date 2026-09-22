"""T012 and T013: the guided run, and whether it finds a number it was never told.

The simulator gives each window a dead time, a non-linear travel and different
speeds per direction, none of which the app can see through the bridge port.
Convergence on those values from presses alone is the proof that calibration
works; everything else in this feature is bookkeeping around it.

The presses here are **jittered**. Pressing at the exact right instant would
demonstrate a precision no person will reproduce, and would hide the reason the
median is there at all.
"""

from __future__ import annotations

import random

import pytest

from somfy_shutters.calibration import ActiveRun, derive
from somfy_shutters.models import Direction, RunKind

REACTION_MEAN = 0.28
REACTION_SPREAD = 0.12


class Presser:
    """A person watching a window: late by a variable amount, every time."""

    def __init__(self, seed: int = 20260922) -> None:
        self._rng = random.Random(seed)

    def reaction(self) -> float:
        return max(0.05, self._rng.gauss(REACTION_MEAN, REACTION_SPREAD))


def simulate_run(
    *,
    true_dead: float,
    true_travel: float,
    presser: Presser,
    established: float | None,
    direction: Direction = Direction.UP,
) -> object:
    """One run, as the API would record it, on a synthetic clock."""
    start = 1000.0
    run = ActiveRun(
        shutter_id="schlafzimmer",
        direction=direction,
        started_monotonic=start,
        expected_total=established or true_travel,
        kind=RunKind.GUIDED,
    )
    # the press when movement is seen: after the real dead time, plus reaction
    run.mark_moving(start + true_dead + presser.reaction())
    # the press on arrival: after the real travel, plus reaction
    arrival = start + true_dead + true_travel + presser.reaction()
    return run.finish(arrival, established)


@pytest.mark.parametrize(
    ("true_dead", "true_travel"),
    [(0.5, 12.0), (0.66, 15.5), (0.74, 18.2)],
)
def test_three_runs_land_within_a_second(true_dead: float, true_travel: float) -> None:
    presser = Presser()
    runs = []
    established = None
    for _ in range(3):
        run = simulate_run(
            true_dead=true_dead,
            true_travel=true_travel,
            presser=presser,
            established=established,
        )
        runs.append(run)
        derived = derive(runs)
        established = derived.travel_seconds if derived else None

    measured = derive(runs).travel_seconds
    truth = true_dead + true_travel  # the run measures command to arrival
    assert abs(measured - truth) < 1.0, f"measured {measured:.2f} against {truth:.2f}"


def test_the_error_is_reaction_time_not_a_bug() -> None:
    """Measured time should be *longer* than the truth, by about one reaction."""
    presser = Presser()
    runs = [
        simulate_run(true_dead=0.6, true_travel=17.4, presser=presser, established=None)
        for _ in range(9)
    ]
    measured = derive(runs).travel_seconds
    truth = 0.6 + 17.4
    assert measured > truth
    assert abs((measured - truth) - REACTION_MEAN) < 0.25


def test_the_median_beats_one_badly_late_press() -> None:
    presser = Presser()
    good = [
        simulate_run(true_dead=0.6, true_travel=17.4, presser=presser, established=None)
        for _ in range(2)
    ]
    established = derive(good).travel_seconds
    # someone walks away and presses four seconds late — still inside the
    # plausibility band, so it is kept and the median has to absorb it
    late = simulate_run(
        true_dead=0.6,
        true_travel=21.4,
        presser=presser,
        established=established,
    )
    assert late.rejected is None
    measured = derive([*good, late]).travel_seconds
    assert abs(measured - 18.0) < 1.0, "the median must not follow the late run"


def test_dead_time_is_measured_too() -> None:
    presser = Presser()
    runs = [
        simulate_run(true_dead=0.74, true_travel=18.2, presser=presser, established=None)
        for _ in range(5)
    ]
    dead = derive(runs).dead_seconds
    assert abs(dead - (0.74 + REACTION_MEAN)) < 0.25


def test_directions_converge_separately() -> None:
    """FR-014: up and down are different numbers and must stay apart."""
    presser = Presser()
    up = [
        simulate_run(true_dead=0.6, true_travel=17.4, presser=presser, established=None)
        for _ in range(3)
    ]
    down = [
        simulate_run(
            true_dead=0.5,
            true_travel=15.5,
            presser=presser,
            established=None,
            direction=Direction.DOWN,
        )
        for _ in range(3)
    ]
    assert abs(derive(up).travel_seconds - 18.0) < 1.0
    assert abs(derive(down).travel_seconds - 16.0) < 1.0
    assert derive(up).travel_seconds - derive(down).travel_seconds > 1.0
