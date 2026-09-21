"""T035: all six rows of the FR-017 precedence table (research.md, section 5).

A report from Pi-Somfy is not a measurement — it is Pi-Somfy's own dead
reckoning. Precedence therefore goes to whoever knows more about what caused the
movement, not to whoever spoke last.
"""

from __future__ import annotations

from somfy_shutters.models import Confidence, Source

WOHNZIMMER = "0x279621"


async def test_report_is_ignored_while_our_command_travels(tracker, clock, events) -> None:
    """Row 1. We know exactly when we sent it; the bridge's timer started later."""
    await tracker._settle("wohnzimmer", 0, Source.COMMAND)
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(9.0)
    events.clear()

    await tracker.handle_report(WOHNZIMMER, 40)

    assert tracker.position("wohnzimmer").percent == 50  # our interpolation, untouched
    assert events == []


async def test_end_stop_report_becomes_certain(tracker, clock) -> None:
    """Row 2. An end stop is mechanically true whoever reports it."""
    await tracker._settle("wohnzimmer", 62, Source.COMMAND)
    await tracker.handle_report(WOHNZIMMER, 0)

    position = tracker.position("wohnzimmer")
    assert position.percent == 0
    assert position.confidence is Confidence.CERTAIN
    assert position.certain_at == clock.now()


async def test_small_difference_is_ignored(tracker, events) -> None:
    """Row 3. Noise between two estimates; moving the graphic would be churn."""
    await tracker._settle("wohnzimmer", 62, Source.COMMAND)
    events.clear()

    await tracker.handle_report(WOHNZIMMER, 63)
    await tracker.handle_report(WOHNZIMMER, 65)  # still within 3 pp of 62

    assert tracker.position("wohnzimmer").percent == 62
    assert events == []


async def test_large_difference_corrects_without_refreshing_the_clock(
    tracker, clock, events
) -> None:
    """Row 4. The report wins, but a second estimate is not fresh knowledge."""
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.0)
    await tracker.tick()
    certain_at = tracker.position("wohnzimmer").certain_at
    await tracker._settle("wohnzimmer", 62, Source.COMMAND)
    clock.advance(3600)
    events.clear()

    await tracker.handle_report(WOHNZIMMER, 48)

    position = tracker.position("wohnzimmer")
    assert position.percent == 48
    assert position.confidence is Confidence.ESTIMATED
    assert position.certain_at == certain_at, (
        "accepting a report must not reset the certainty clock"
    )
    assert [e["type"] for e in events] == ["correction"]
    assert events[0]["ease_ms"] == 400


async def test_a_report_stream_is_treated_as_external_movement(tracker, clock) -> None:
    """Row 5. A physical remote was used: Pi-Somfy heard it and we did not, so
    its clock is genuinely fresher than ours."""
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.0)
    await tracker.tick()
    await tracker._settle("wohnzimmer", 62, Source.COMMAND)
    clock.advance(3600)
    before = tracker.position("wohnzimmer").certain_at

    await tracker.handle_report(WOHNZIMMER, 55)
    clock.advance(1.0)
    await tracker.handle_report(WOHNZIMMER, 45)

    position = tracker.position("wohnzimmer")
    assert position.percent == 45
    assert position.confidence is Confidence.ESTIMATED
    assert position.certain_at == clock.now()
    assert position.certain_at != before
    assert position.source is Source.REPORT


async def test_report_for_an_unknown_address_is_dropped(tracker, events) -> None:
    """Row 6."""
    await tracker._settle("wohnzimmer", 62, Source.COMMAND)
    events.clear()

    await tracker.handle_report("0xabcdef", 10)

    assert tracker.position("wohnzimmer").percent == 62
    assert events == []


async def test_reports_during_travel_do_not_poison_the_next_decision(tracker, clock) -> None:
    """A report seen while travelling is remembered, but must not itself make the
    next idle report look like external movement."""
    await tracker._settle("wohnzimmer", 0, Source.COMMAND)
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(9.0)
    await tracker.handle_report(WOHNZIMMER, 40)
    clock.advance(9.0)
    await tracker.tick()

    assert tracker.position("wohnzimmer").confidence is Confidence.CERTAIN
    assert tracker.position("wohnzimmer").percent == 100
