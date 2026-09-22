"""The travel curve is a coordinate transform, and every path has to agree on it.

Found in review after the curve became a transform: a curve given without a
measurement vanished on restart, a stop used the up-curve for a shutter going
down, and a report read while idle ignored which way the shutter had moved.
"""

from __future__ import annotations

import pytest

from somfy_shutters.calibration import to_level, to_percent
from somfy_shutters.calibration_store import CalibrationService, CalibrationStore
from somfy_shutters.config import Settings
from somfy_shutters.models import CheckReply, Direction

from .test_calibration_precedence import CONFIG

UP_A, DOWN_A = 1.3, 0.8


@pytest.fixture
def bent(tracker):
    """Different shapes per direction, the case where picking the wrong one shows."""
    tracker._curve_a = lambda _sid, d: UP_A if d is Direction.UP else DOWN_A
    return tracker


def test_a_curve_without_a_measurement_survives_a_restart(tmp_path) -> None:
    settings = Settings.model_validate(CONFIG)
    store = CalibrationStore(tmp_path / "state.db", tmp_path / "calibration.toml")
    CalibrationService(settings, store).answer_check("kueche", Direction.UP, CheckReply("too_low"))
    store.close()

    store2 = CalibrationStore(tmp_path / "state.db", tmp_path / "calibration.toml")
    revived = CalibrationService(settings, store2)
    try:
        assert revived.curve_a("kueche", Direction.UP) == pytest.approx(1.05)
        assert revived.effective("kueche", Direction.UP).source == "default"
    finally:
        store2.close()


async def test_a_stop_on_the_way_down_uses_the_down_curve(bent, clock) -> None:
    await bent._settle("wohnzimmer", 100, bent.position("wohnzimmer").source)
    movement = await bent.start_movement("wohnzimmer", 0)
    assert movement.curve_a == DOWN_A
    clock.advance(movement.duration_seconds / 2)

    level = bent.halt_level("wohnzimmer")
    assert level == 50, "halfway through the time is halfway through the level"
    position = await bent.stop("wohnzimmer")
    assert position.percent == round(to_percent(50, DOWN_A))


async def test_halt_and_settle_describe_the_same_place(bent, clock) -> None:
    await bent._settle("wohnzimmer", 0, bent.position("wohnzimmer").source)
    movement = await bent.start_movement("wohnzimmer", 100)
    clock.advance(movement.duration_seconds * 0.3)
    level = bent.halt_level("wohnzimmer")
    position = await bent.stop("wohnzimmer")
    assert abs(position.percent - to_percent(level, UP_A)) <= 1


async def test_an_idle_report_below_the_estimate_is_read_as_going_down(bent) -> None:
    await bent._settle("wohnzimmer", 60, bent.position("wohnzimmer").source)
    bent._last_direction["wohnzimmer"] = Direction.UP
    here = to_level(60, UP_A)
    assert bent.percent_from_level("wohnzimmer", round(here) - 20) == round(
        to_percent(round(here) - 20, DOWN_A)
    )
    assert bent.percent_from_level("wohnzimmer", round(here) + 20) == round(
        to_percent(round(here) + 20, UP_A)
    )


async def test_a_report_during_travel_uses_the_travel_direction(bent) -> None:
    await bent._settle("wohnzimmer", 100, bent.position("wohnzimmer").source)
    await bent.start_movement("wohnzimmer", 0)
    assert bent.percent_from_level("wohnzimmer", 70) == round(to_percent(70, DOWN_A))


async def test_holding_position_keeps_the_last_direction(bent) -> None:
    await bent._settle("wohnzimmer", 40, bent.position("wohnzimmer").source)
    bent._last_direction["wohnzimmer"] = Direction.DOWN
    assert bent.level_for("wohnzimmer", 40) == round(to_level(40, DOWN_A))
