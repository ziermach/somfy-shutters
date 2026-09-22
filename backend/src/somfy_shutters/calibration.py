"""Measuring how long a shutter takes, and what to believe about the result.

No I/O here, like `tracker.py`. Everything below is arithmetic over runs plus a
small state machine, which is what makes the invariants cheap to test — in
particular the one that matters: a verification curve may bend the middle of a
travel and may never move its end points.

What this module does **not** do is make a position more certain. A measured
travel time improves the estimate; only reaching an end stop makes a position
known (constitution III).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median

from .models import CheckAnswer, Direction, MeasurementRun, RunKind, utcnow

# --- rules, quoted from data-model.md ---------------------------------------

MIN_TOTAL_SECONDS = 1.0
PLAUSIBLE_LOW = 0.5
PLAUSIBLE_HIGH = 2.0
ABANDON_FACTOR = 2.0
RETAIN_RUNS = 10
"""How many recent valid runs feed the median. Bounded so a genuine change in
the shutter is followed, while a single outlier is not (FR-021)."""

CURVE_STEP = 0.1
CURVE_BOUND = 0.8
CONFIRM_COOLDOWN_HOURS = 24

CONTRARY_DELTA = 3
"""How far a report must move against the run's direction to count as somebody
else driving. Anything smaller is noise between two estimates."""


class RejectionReason:
    DEAD_AFTER_ARRIVAL = "dead_after_arrival"
    TOO_SHORT = "too_short"
    IMPLAUSIBLE = "implausible"
    DISTURBED = "disturbed"
    ABANDONED = "abandoned"


# --- the curve ---------------------------------------------------------------


def travel_curve(progress: float, k: float) -> float:
    """Map linear progress to displayed progress.

    ``k = 0`` is the linear behaviour of feature 001. For every ``k`` within
    ±1 this passes through exactly 0 and 1 and stays monotonic, so end points
    cannot drift and the display never runs backwards — by construction, not by
    a clamp somebody could forget (FR-025).
    """
    return progress - (k * math.sin(2 * math.pi * progress)) / (2 * math.pi)


def clamp_curve(k: float) -> float:
    return max(-CURVE_BOUND, min(CURVE_BOUND, k))


def curve_from_answers(answers: list[CheckAnswer]) -> float:
    """Accumulate check answers into one shape parameter.

    "Too high" means the shutter is lower than shown, so the displayed middle
    has to come down: k decreases.
    """
    k = 0.0
    for answer in answers:
        if answer.answer == "too_high":
            k -= CURVE_STEP
        elif answer.answer == "too_low":
            k += CURVE_STEP
    return clamp_curve(k)


def at_curve_limit(k: float) -> bool:
    return abs(k) >= CURVE_BOUND - 1e-9


# --- judging a run -----------------------------------------------------------


def rejection_for(
    dead_seconds: float,
    total_seconds: float,
    established_total: float | None,
) -> str | None:
    """Why this run does not count, or None when it does."""
    if dead_seconds >= total_seconds:
        return RejectionReason.DEAD_AFTER_ARRIVAL
    if total_seconds < MIN_TOTAL_SECONDS:
        return RejectionReason.TOO_SHORT
    if established_total is not None and not (
        established_total * PLAUSIBLE_LOW <= total_seconds <= established_total * PLAUSIBLE_HIGH
    ):
        return RejectionReason.IMPLAUSIBLE
    return None


# --- deriving the stored value ----------------------------------------------


@dataclass(frozen=True)
class Derived:
    travel_seconds: float
    dead_seconds: float
    runs: int
    updated_at: datetime


def derive(runs: list[MeasurementRun], now: datetime | None = None) -> Derived | None:
    """The median of the recent valid runs — never the mean (FR-013).

    The mean would let one late press drag the value; the median needs two bad
    runs out of three before it moves, which is exactly the protection a human
    with a reaction time needs.
    """
    valid = [r for r in runs if r.rejected is None][-RETAIN_RUNS:]
    if not valid:
        return None
    return Derived(
        travel_seconds=float(median(r.total_seconds for r in valid)),
        dead_seconds=float(median(r.dead_seconds for r in valid)),
        runs=len(valid),
        updated_at=now or utcnow(),
    )


# --- the guided run ----------------------------------------------------------


@dataclass
class ActiveRun:
    """In memory only. A run interrupted by a restart is lost, and should be:
    its arrival was never observed."""

    shutter_id: str
    direction: Direction
    started_monotonic: float
    expected_total: float
    dead_monotonic: float | None = None
    disturbed: bool = False
    kind: RunKind = RunKind.GUIDED
    last_report: int | None = None

    @property
    def phase(self) -> str:
        return "timing" if self.dead_monotonic is not None else "waiting_for_movement"

    def note_report(self, percent: int) -> None:
        """A position report arrived while this run is in progress.

        The bridge narrates our own travel — it publishes a position roughly
        every second while the shutter moves, because we told it to move. Those
        reports are expected and must not invalidate the run; an earlier version
        treated any of them as interference and would have rejected every real
        measurement.

        What does mean interference is a report moving *against* the direction
        we commanded: nothing we did could produce that.
        """
        if self.last_report is not None:
            delta = percent - self.last_report
            against = (
                delta < -CONTRARY_DELTA
                if self.direction is Direction.UP
                else delta > CONTRARY_DELTA
            )
            if against:
                self.disturbed = True
        self.last_report = percent

    def mark_moving(self, now_monotonic: float) -> float:
        self.dead_monotonic = now_monotonic
        return now_monotonic - self.started_monotonic

    def elapsed(self, now_monotonic: float) -> float:
        return now_monotonic - self.started_monotonic

    def is_abandoned(self, now_monotonic: float) -> bool:
        return self.elapsed(now_monotonic) > self.expected_total * ABANDON_FACTOR

    def finish(
        self,
        now_monotonic: float,
        established_total: float | None,
        recorded_at: datetime | None = None,
    ) -> MeasurementRun:
        total = self.elapsed(now_monotonic)
        dead = (
            self.dead_monotonic - self.started_monotonic if self.dead_monotonic is not None else 0.0
        )
        reason = (
            RejectionReason.DISTURBED
            if self.disturbed
            else rejection_for(dead, total, established_total)
        )
        return MeasurementRun(
            shutter_id=self.shutter_id,
            direction=self.direction,
            dead_seconds=round(dead, 3),
            total_seconds=round(total, 3),
            recorded_at=recorded_at or utcnow(),
            kind=self.kind,
            rejected=reason,
        )


class CalibrationError(RuntimeError):
    """A calibration request that cannot be honoured, with a machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class RunRegistry:
    """Which shutters are being measured right now."""

    _active: dict[str, ActiveRun] = field(default_factory=dict)

    def get(self, shutter_id: str) -> ActiveRun | None:
        return self._active.get(shutter_id)

    def start(self, run: ActiveRun) -> ActiveRun:
        if run.shutter_id in self._active:
            raise CalibrationError(
                "already_running", "Für diesen Rolladen läuft schon eine Messung."
            )
        self._active[run.shutter_id] = run
        return run

    def finish(self, shutter_id: str) -> ActiveRun:
        run = self._active.pop(shutter_id, None)
        if run is None:
            raise CalibrationError("no_run", "Für diesen Rolladen läuft keine Messung.")
        return run

    def disturb(self, shutter_id: str) -> None:
        """Called when something else commands a shutter under measurement."""
        run = self._active.get(shutter_id)
        if run is not None:
            run.disturbed = True

    def note_report(self, shutter_id: str, percent: int) -> None:
        run = self._active.get(shutter_id)
        if run is not None:
            run.note_report(percent)

    def is_measuring(self, shutter_id: str) -> bool:
        return shutter_id in self._active


# --- the one-tap confirmation ------------------------------------------------


@dataclass
class PendingConfirmation:
    """A travel that ran end to end, waiting for somebody to say it arrived.

    The started_monotonic is what makes the tap a measurement: the elapsed time
    from command to tap is the only number in this feature that nothing else in
    the system could have produced.
    """

    shutter_id: str
    direction: Direction
    started_monotonic: float
    asked_at: datetime


def may_ask_for_confirmation(
    *,
    was_end_to_end: bool,
    was_interrupted: bool,
    initiated_by_us: bool,
    last_asked: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Whether a finished travel is worth one question (FR-018, FR-018a).

    No measurement is ever derived from a travel alone — the arrival time we
    computed is the travel time we are trying to measure. Only a person saying
    "yes, it is up" is an observation.
    """
    if not (was_end_to_end and initiated_by_us) or was_interrupted:
        return False
    if last_asked is None:
        return True
    hours = ((now or utcnow()) - last_asked).total_seconds() / 3600
    return hours >= CONFIRM_COOLDOWN_HOURS


# --- the guided flow, composed ----------------------------------------------


@dataclass
class RunStart:
    direction: Direction
    from_percent: int
    expected_total: float


def plan_run(current_percent: int | None, established: dict[str, float]) -> RunStart:
    """Which direction the next run goes, and how long it should take.

    Runs alternate on their own because each starts from the end stop the last
    one reached (FR-006). A shutter that is not at an end stop cannot start one
    at all — the caller checks that first and offers the homing drive.
    """
    if current_percent not in (0, 100):
        raise CalibrationError(
            "not_at_end_stop",
            "Die Messung muss an einer Endlage beginnen.",
        )
    direction = Direction.UP if current_percent == 0 else Direction.DOWN
    return RunStart(
        direction=direction,
        from_percent=current_percent,
        expected_total=established.get(direction.value, 0.0),
    )


def nearest_end_stop(current_percent: int | None) -> int:
    """Where a homing drive goes. An unknown position has no nearest one — open."""
    if current_percent is None:
        return 100
    return 100 if current_percent >= 50 else 0
