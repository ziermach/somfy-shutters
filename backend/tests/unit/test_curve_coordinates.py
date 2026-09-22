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


async def test_a_reversal_mid_window_is_sent_relative_to_the_bridge_counter(bent, clock) -> None:
    """The bridge runs for (new level - its counter). After going down to 50 %
    its counter sits where the down-curve put it, not where the up-curve would
    place 50 % — an absolute level made the two sides disagree about the
    distance, and the app declared arrival while the motor was still running."""
    await bent._settle("wohnzimmer", 100, bent.position("wohnzimmer").source)
    level = bent.level_for("wohnzimmer", 50)
    down = await bent.start_movement("wohnzimmer", 50, level)
    clock.advance(down.duration_seconds + 0.1)
    await bent.tick()
    counter = bent.bridge_level("wohnzimmer")
    assert counter == level == round(to_level(50, DOWN_A))

    sent = bent.level_for("wohnzimmer", 75)
    travel = to_level(75, UP_A) - to_level(50, UP_A)
    assert sent == round(counter + travel)
    up = await bent.start_movement("wohnzimmer", 75, sent)
    # Bridge's run and ours now describe the same distance.
    full_up = bent._travel_seconds("wohnzimmer", Direction.UP)
    assert up.duration_seconds == pytest.approx(full_up * travel / 100)
    assert abs((sent - counter) / 100 * full_up - up.duration_seconds) < full_up * 0.01


async def test_end_stops_are_sent_as_end_stops(bent, clock) -> None:
    await bent._settle("wohnzimmer", 100, bent.position("wohnzimmer").source)
    await bent.start_movement("wohnzimmer", 30)
    clock.advance(60)
    await bent.tick()
    assert bent.level_for("wohnzimmer", 100) == 100
    assert bent.level_for("wohnzimmer", 0) == 0


async def test_a_halt_resets_the_counter_to_where_the_bridge_stopped(bent, clock) -> None:
    await bent._settle("wohnzimmer", 0, bent.position("wohnzimmer").source)
    movement = await bent.start_movement("wohnzimmer", 100)
    clock.advance(movement.duration_seconds / 4)
    halt = bent.halt_level("wohnzimmer")
    await bent.stop("wohnzimmer")
    assert bent.bridge_level("wohnzimmer") == pytest.approx(halt, abs=0.5)


async def test_an_end_stop_waits_for_the_bridge_timer(bent, clock) -> None:
    """Up from a midpoint reached going down: the bridge's counter lags the
    up-curve, and it times the motor on that counter. Arrival is when both
    are done, or the next command meets a bridge still counting."""
    await bent._settle("wohnzimmer", 100, bent.position("wohnzimmer").source)
    level = bent.level_for("wohnzimmer", 50)
    down = await bent.start_movement("wohnzimmer", 50, level)
    clock.advance(down.duration_seconds + 0.1)
    await bent.tick()

    up = await bent.start_movement("wohnzimmer", 100, bent.level_for("wohnzimmer", 100))
    full_up = bent._travel_seconds("wohnzimmer", Direction.UP)
    bridge_run = full_up * (100 - level) / 100
    curve_run = full_up * (100 - to_level(50, UP_A)) / 100
    assert bridge_run > curve_run, "the case only exists when the counter lags"
    assert up.duration_seconds == pytest.approx(bridge_run)
