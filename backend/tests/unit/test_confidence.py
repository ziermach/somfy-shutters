"""T034: every transition from the state diagram in data-model.md."""

from __future__ import annotations

from somfy_shutters.models import Confidence, Source


async def test_starts_unknown_with_nothing_stored(tracker) -> None:
    assert tracker.position("wohnzimmer").confidence is Confidence.UNKNOWN


async def test_reaching_an_end_stop_makes_it_certain(tracker, clock) -> None:
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.0)
    await tracker.tick()
    position = tracker.position("wohnzimmer")
    assert position.confidence is Confidence.CERTAIN
    assert position.percent == 100
    assert position.certain_at == clock.now()


async def test_leaving_an_end_stop_makes_it_an_estimate(tracker, clock) -> None:
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.0)
    await tracker.tick()
    certain_at = tracker.position("wohnzimmer").certain_at

    await tracker.start_movement("wohnzimmer", 50)
    clock.advance(8.0)
    await tracker.tick()

    position = tracker.position("wohnzimmer")
    assert position.confidence is Confidence.ESTIMATED
    # The clock does not restart: certainty is as old as the last end stop.
    assert position.certain_at == certain_at


async def test_an_estimate_goes_stale_on_age_alone(tracker, clock) -> None:
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.0)
    await tracker.tick()
    await tracker.start_movement("wohnzimmer", 50)
    clock.advance(8.0)
    await tracker.tick()

    assert tracker.is_stale("wohnzimmer") is False
    clock.advance(13 * 3600)
    assert tracker.is_stale("wohnzimmer") is True


async def test_a_certain_position_never_goes_stale(tracker, clock) -> None:
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.0)
    await tracker.tick()
    clock.advance(30 * 24 * 3600)
    assert tracker.is_stale("wohnzimmer") is False


async def test_nearest_end_stop(tracker, clock) -> None:
    await tracker._settle("wohnzimmer", 70, Source.COMMAND)
    assert tracker.nearest_end_stop("wohnzimmer") == 100
    await tracker._settle("wohnzimmer", 20, Source.COMMAND)
    assert tracker.nearest_end_stop("wohnzimmer") == 0


async def test_unknown_position_resyncs_upward(tracker) -> None:
    """There is no nearest end stop when the position is unknown — pick one and say so."""
    assert tracker.nearest_end_stop("schlafzimmer") == 100


async def test_settling_at_an_intermediate_position_is_never_certain(tracker) -> None:
    await tracker._settle("wohnzimmer", 62, Source.COMMAND)
    assert tracker.position("wohnzimmer").confidence is Confidence.ESTIMATED
