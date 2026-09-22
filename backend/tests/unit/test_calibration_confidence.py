"""T010: calibration improves the estimate. It never improves the confidence.

This is the one way feature 002 could damage feature 001's central promise. A
person who has just measured a shutter six times will feel the number is now
known; between end stops it is still dead reckoning, and the system must keep
saying so.
"""

from __future__ import annotations

from somfy_shutters.calibration_store import CalibrationService, CalibrationStore
from somfy_shutters.config import Settings
from somfy_shutters.models import Confidence, Direction, MeasurementRun, RunKind, utcnow
from somfy_shutters.store import Store
from somfy_shutters.tracker import Tracker

from ..conftest import CONFIG, FakeClock


def build(tmp_path, clock: FakeClock, *, calibrated: bool) -> Tracker:
    settings = Settings.model_validate(CONFIG)
    cal_store = CalibrationStore(tmp_path / "state.db", tmp_path / "calibration.toml")
    service = CalibrationService(settings, cal_store)
    if calibrated:
        for _ in range(3):
            service.record(
                MeasurementRun(
                    shutter_id="wohnzimmer",
                    direction=Direction.UP,
                    dead_seconds=0.7,
                    total_seconds=18.0,
                    kind=RunKind.GUIDED,
                    recorded_at=utcnow(),
                )
            )

    async def emit(event: dict) -> None:
        return None

    return Tracker(
        settings,
        Store(tmp_path / "state.db"),
        emit=emit,
        monotonic=clock.monotonic,
        clock=clock.now,
        calibration=service,
    )


async def test_a_calibrated_shutter_is_still_only_estimated_mid_travel(tmp_path) -> None:
    clock = FakeClock()
    tracker = build(tmp_path, clock, calibrated=True)

    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.0)
    await tracker.tick()
    assert tracker.position("wohnzimmer").confidence is Confidence.CERTAIN

    await tracker.start_movement("wohnzimmer", 50)
    clock.advance(9.0)
    await tracker.tick()

    position = tracker.position("wohnzimmer")
    assert position.confidence is Confidence.ESTIMATED, (
        "measuring the travel time does not make the position known"
    )


async def test_calibration_does_not_touch_the_certainty_clock(tmp_path) -> None:
    clock = FakeClock()
    tracker = build(tmp_path, clock, calibrated=True)

    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.0)
    await tracker.tick()
    certain_at = tracker.position("wohnzimmer").certain_at

    await tracker.start_movement("wohnzimmer", 40)
    clock.advance(11.0)
    await tracker.tick()

    assert tracker.position("wohnzimmer").certain_at == certain_at


async def test_an_uncalibrated_shutter_is_fully_operable(tmp_path) -> None:
    """FR-027: never a precondition for anything."""
    clock = FakeClock()
    tracker = build(tmp_path, clock, calibrated=False)

    movement = await tracker.start_movement("schlafzimmer", 100)
    assert movement is not None
    assert movement.duration_seconds == 20.0  # the stated default


async def test_the_measured_time_reaches_the_animation(tmp_path) -> None:
    """Schlafzimmer has no hand-written value, so a measurement is what changes it."""
    clock = FakeClock()
    settings = Settings.model_validate(CONFIG)
    cal_store = CalibrationStore(tmp_path / "state.db", tmp_path / "calibration.toml")
    service = CalibrationService(settings, cal_store)

    async def emit(event: dict) -> None:
        return None

    tracker = Tracker(
        settings,
        Store(tmp_path / "state.db"),
        emit=emit,
        monotonic=clock.monotonic,
        clock=clock.now,
        calibration=service,
    )

    assert tracker._travel_seconds("schlafzimmer", Direction.UP) == 20.0  # the default

    for _ in range(3):
        service.record(
            MeasurementRun(
                shutter_id="schlafzimmer",
                direction=Direction.UP,
                dead_seconds=0.7,
                total_seconds=15.0,
                kind=RunKind.GUIDED,
                recorded_at=utcnow(),
            )
        )

    assert tracker._travel_seconds("schlafzimmer", Direction.UP) == 15.0
    movement = await tracker.start_movement("schlafzimmer", 100)
    assert movement.duration_seconds == 15.0, "the animation must use the measurement at once"


async def test_a_measurement_cannot_override_a_hand_written_value(tmp_path) -> None:
    """Wohnzimmer carries travel_up_seconds = 18.0 in shutters.toml."""
    clock = FakeClock()
    settings = Settings.model_validate(CONFIG)
    cal_store = CalibrationStore(tmp_path / "state.db", tmp_path / "calibration.toml")
    service = CalibrationService(settings, cal_store)

    async def emit(event: dict) -> None:
        return None

    tracker = Tracker(
        settings,
        Store(tmp_path / "state.db"),
        emit=emit,
        monotonic=clock.monotonic,
        clock=clock.now,
        calibration=service,
    )

    for _ in range(3):
        service.record(
            MeasurementRun(
                shutter_id="wohnzimmer",
                direction=Direction.UP,
                dead_seconds=0.7,
                total_seconds=25.0,
                kind=RunKind.GUIDED,
                recorded_at=utcnow(),
            )
        )

    assert tracker._travel_seconds("wohnzimmer", Direction.UP) == 18.0
    assert service.effective("wohnzimmer", Direction.UP).source == "manual"
