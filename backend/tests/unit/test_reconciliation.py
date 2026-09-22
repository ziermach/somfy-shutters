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


async def test_the_bridge_finishing_our_command_is_not_a_correction(tracker, clock, events) -> None:
    """Our travel ended by our clock; the bridge is still counting through the same
    command. Found clicking "auf" on the overview: the card jumped back and climbed
    in one-second steps, and the bridge's progress read as a physical remote."""
    await tracker._settle("wohnzimmer", 0, Source.COMMAND)
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.5)
    await tracker.tick()
    settled = tracker.position("wohnzimmer")
    events.clear()

    for level in (60, 75, 90, 100):
        await tracker.handle_report(WOHNZIMMER, level)
        clock.advance(1.0)

    assert events == []
    assert tracker.position("wohnzimmer") == settled, "certain_at must not be refreshed"
    assert tracker.bridge_level("wohnzimmer") == 100


async def test_once_the_bridge_has_arrived_a_report_is_news_again(tracker, clock, events) -> None:
    await tracker._settle("wohnzimmer", 0, Source.COMMAND)
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.5)
    await tracker.tick()
    await tracker.handle_report(WOHNZIMMER, 100)  # the bridge's run ends here
    events.clear()

    await tracker.handle_report(WOHNZIMMER, 40)
    assert [e["type"] for e in events] == ["correction"]


async def test_after_the_window_a_report_is_news_again(tracker, clock, events) -> None:
    await tracker._settle("wohnzimmer", 0, Source.COMMAND)
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.0 * 1.5 + 3)
    await tracker.tick()
    events.clear()

    await tracker.handle_report(WOHNZIMMER, 60)
    assert [e["type"] for e in events] == ["correction"]


async def test_a_report_off_the_bridges_way_is_still_news(tracker, clock, events) -> None:
    await tracker._settle("wohnzimmer", 100, Source.COMMAND)
    await tracker.start_movement("wohnzimmer", 50)
    clock.advance(10.0)
    await tracker.tick()
    events.clear()

    await tracker.handle_report(WOHNZIMMER, 20)  # below where we sent it
    assert [e["type"] for e in events] == ["correction"]


async def test_an_unknown_counter_stays_unknown_through_a_reversal(tracker, clock, events) -> None:
    """Unknown position, "zu", then "auf" half a second later. The first travel's
    start was assumed, so the counter derived from it is too — the bridge may
    well be climbing from the bottom. Its reports on the way up are its own run."""
    assert tracker.position("wohnzimmer").percent is None
    await tracker.start_movement("wohnzimmer", 0)
    clock.advance(0.5)
    assert tracker.bridge_level("wohnzimmer") is None
    up = await tracker.start_movement("wohnzimmer", 100)
    assert up.duration_seconds == 18.0, "a whole window, since the bridge may run one"
    assert up.from_percent == 0, "the 96 % it had reached was part of the same guess"
    clock.advance(18.5)
    await tracker.tick()
    events.clear()

    for level in (4, 30, 70):
        await tracker.handle_report(WOHNZIMMER, level)
        clock.advance(1.0)
    assert events == []


async def test_after_a_restart_the_counter_starts_from_the_stored_position(
    tracker, settings, store, clock
) -> None:
    """Otherwise every first command after a restart would count as unknown and
    animate from the far end, however well the position was known."""
    from somfy_shutters.tracker import Tracker

    await tracker._settle("wohnzimmer", 0, Source.COMMAND)
    movement = await tracker.start_movement("wohnzimmer", 60)
    clock.advance(movement.duration_seconds + 0.1)
    await tracker.tick()

    async def emit(event: dict) -> None:
        pass

    revived = Tracker(settings, store, emit=emit, monotonic=clock.monotonic, clock=clock.now)
    assert revived.bridge_level("wohnzimmer") == 60
    again = await revived.start_movement("wohnzimmer", 80)
    assert again.from_percent == 60


# --- feature 006: retained reports and movement reports --------------------------

from somfy_shutters.bridge.base import Report  # noqa: E402


async def test_retained_position_leaves_a_known_position_alone(tracker, events) -> None:
    await tracker._settle("wohnzimmer", 62, Source.COMMAND)
    events.clear()
    await tracker.handle(Report(WOHNZIMMER, 40, retained=True))
    assert tracker.position("wohnzimmer").percent == 62
    assert events == []
    assert tracker.bridge_level("wohnzimmer") == 40, "the bridge's counter is still worth knowing"


async def test_retained_position_fills_an_unknown_one_as_an_estimate(tracker) -> None:
    assert tracker.position("wohnzimmer").percent is None
    await tracker.handle(Report(WOHNZIMMER, 100, retained=True))
    position = tracker.position("wohnzimmer")
    assert position.percent == 100
    assert position.confidence is Confidence.ESTIMATED, "old news is never certain, not even at 100"


async def test_retained_movement_is_ignored(tracker, events) -> None:
    await tracker._settle("wohnzimmer", 62, Source.COMMAND)
    before = tracker.position("wohnzimmer").certain_at
    events.clear()
    await tracker.handle(Report(WOHNZIMMER, kind="movement", state="closing", retained=True))
    assert events == [] and "wohnzimmer" not in tracker._external_moving
    await tracker.handle_report(WOHNZIMMER, 50)
    assert events[-1]["type"] == "correction"
    assert tracker.position("wohnzimmer").certain_at == before, (
        "an ordinary correction keeps the age"
    )


async def test_live_opening_we_did_not_cause_is_a_physical_remote(tracker, clock, events) -> None:
    await tracker._settle("wohnzimmer", 0, Source.COMMAND)
    before = tracker.position("wohnzimmer").certain_at
    clock.advance(600)
    events.clear()

    await tracker.handle(Report(WOHNZIMMER, kind="movement", state="opening"))
    after_opening = tracker.position("wohnzimmer")
    assert after_opening.confidence is Confidence.ESTIMATED, "it left the end stop"
    assert after_opening.certain_at > before, "the bridge heard the command: its clock is fresh"

    # One report is enough now — no two-report guess, no noise filter.
    await tracker.handle_report(WOHNZIMMER, 2)
    assert tracker.position("wohnzimmer").percent == 2
    assert events[-1]["type"] == "correction"

    await tracker.handle(Report(WOHNZIMMER, kind="movement", state="stopped"))
    assert "wohnzimmer" not in tracker._external_moving


async def test_live_opening_during_our_own_travel_is_ours(tracker, events) -> None:
    await tracker._settle("wohnzimmer", 0, Source.COMMAND)
    await tracker.start_movement("wohnzimmer", 100)
    events.clear()
    await tracker.handle(Report(WOHNZIMMER, kind="movement", state="opening"))
    assert "wohnzimmer" not in tracker._external_moving
    assert events == []


async def test_live_closing_during_the_bridge_run_is_ours(tracker, clock) -> None:
    await tracker._settle("wohnzimmer", 100, Source.COMMAND)
    movement = await tracker.start_movement("wohnzimmer", 0)
    clock.advance(movement.duration_seconds + 0.5)
    await tracker.tick()
    await tracker.handle(Report(WOHNZIMMER, kind="movement", state="closing"))
    assert "wohnzimmer" not in tracker._external_moving
