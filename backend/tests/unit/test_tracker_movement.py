"""T020: movement, interpolation, stop, reverse."""

from __future__ import annotations

from somfy_shutters.models import Action, Confidence, Direction


async def test_travel_time_comes_from_configuration(tracker, clock) -> None:
    await tracker._settle("wohnzimmer", 0, tracker.position("wohnzimmer").source)
    movement = await tracker.start_movement("wohnzimmer", 100)
    # 18 s configured for up, full travel
    assert movement.duration_seconds == 18.0
    assert movement.direction is Direction.UP


async def test_partial_travel_is_proportional(tracker) -> None:
    await tracker._settle("wohnzimmer", 0, tracker.position("wohnzimmer").source)
    movement = await tracker.start_movement("wohnzimmer", 50)
    assert movement.duration_seconds == 9.0


async def test_uncalibrated_shutter_still_animates(tracker) -> None:
    """FR-015: a shutter with no measurement uses the stated default, and moves."""
    await tracker._settle("schlafzimmer", 0, tracker.position("schlafzimmer").source)
    movement = await tracker.start_movement("schlafzimmer", 100)
    assert movement is not None
    assert movement.duration_seconds == 20.0  # default_travel_seconds


async def test_half_measured_shutter_uses_default_for_the_other_direction(tracker) -> None:
    await tracker._settle("kueche", 0, tracker.position("kueche").source)
    up = await tracker.start_movement("kueche", 100)
    assert up.duration_seconds == 12.0
    await tracker.stop("kueche")
    await tracker._settle("kueche", 100, tracker.position("kueche").source)
    down = await tracker.start_movement("kueche", 0)
    assert down.duration_seconds == 20.0


async def test_interpolation_reaches_the_target(tracker, clock) -> None:
    await tracker._settle("wohnzimmer", 0, tracker.position("wohnzimmer").source)
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(9.0)
    assert tracker.position("wohnzimmer").percent == 50
    clock.advance(9.0)
    await tracker.tick()
    assert tracker.position("wohnzimmer").percent == 100
    assert tracker.movement("wohnzimmer") is None


async def test_stop_freezes_where_it_is(tracker, clock) -> None:
    """FR-016: not at the original target."""
    await tracker._settle("wohnzimmer", 0, tracker.position("wohnzimmer").source)
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(4.5)
    position = await tracker.stop("wohnzimmer")
    assert position.percent == 25
    assert position.confidence is Confidence.ESTIMATED
    assert tracker.movement("wohnzimmer") is None


async def test_reverse_starts_from_where_it_is(tracker, clock) -> None:
    await tracker._settle("wohnzimmer", 0, tracker.position("wohnzimmer").source)
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(9.0)
    await tracker.stop("wohnzimmer")
    reverse = await tracker.start_movement("wohnzimmer", 0)
    assert reverse.from_percent == 50
    assert reverse.direction is Direction.DOWN
    assert reverse.duration_seconds == 8.0  # half of the 16 s down travel


async def test_commanding_the_current_position_is_a_no_op(tracker) -> None:
    await tracker._settle("wohnzimmer", 100, tracker.position("wohnzimmer").source)
    assert await tracker.start_movement("wohnzimmer", 100) is None


async def test_unknown_position_is_still_drivable(tracker) -> None:
    """It is how a shutter becomes known again — assume the far end."""
    movement = await tracker.start_movement("schlafzimmer", 100)
    assert movement is not None
    assert movement.from_percent == 0
    assert movement.duration_seconds == 20.0


async def test_plan_maps_actions_to_targets(tracker) -> None:
    assert tracker.plan("wohnzimmer", Action.OPEN) == 100
    assert tracker.plan("wohnzimmer", Action.CLOSE) == 0
    assert tracker.plan("wohnzimmer", Action.POSITION, 30) == 30
    assert tracker.plan("wohnzimmer", Action.STOP) is None


async def test_movement_emits_an_event(tracker, events) -> None:
    await tracker._settle("wohnzimmer", 0, tracker.position("wohnzimmer").source)
    events.clear()
    await tracker.start_movement("wohnzimmer", 100)
    assert [e["type"] for e in events] == ["movement"]
