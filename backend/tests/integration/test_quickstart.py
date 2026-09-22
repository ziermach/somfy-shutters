"""T040: the quickstart, walked by machine.

Each test is one scenario from specs/002-travel-calibration/quickstart.md, in
its order, against the running app and the simulated house. Where the document
says to compare against the simulator's hidden truth, these do — through the
simulator-only endpoint, never through the port the app talks to.

What this cannot replace is C4.1's eyes-on pass: colour and layout can imply
certainty without a single field changing.
"""

from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.calibration import CURVE_NEUTRAL, to_level
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

CONFIG = {
    "general": {"default_travel_seconds": 20, "stale_after_hours": 12},
    "bridge": {"kind": "sim"},
    "shutter": [{"id": "flink", "name": "Flink", "address": "0x279631"}],
}

# The simulated window, made fast so a run fits in a test. The app is told none
# of this: it has to find the numbers by measuring.
SIM_DEAD = 0.12
SIM_UP = 1.4
SIM_DOWN = 1.1
REACTION = 0.12


@pytest_asyncio.fixture
async def client(tmp_path):
    settings = Settings.model_validate(CONFIG)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    for shutter in bridge._shutters.values():
        shutter.dead_time = SIM_DEAD
        shutter.travel_up = SIM_UP
        shutter.travel_down = SIM_DOWN
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        http.app = app  # type: ignore[attr-defined]
        yield http


async def park(client, percent: int) -> None:
    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": percent})


async def guided_run(client) -> dict:
    """One run, pressed the way a person would: a little late, both times."""
    started = (await client.post("/api/calibration/flink/run")).json()
    await asyncio.sleep(SIM_DEAD + REACTION)
    await client.post("/api/calibration/flink/mark", json={"mark": "moving"})
    travel = SIM_UP if started["direction"] == "up" else SIM_DOWN
    await asyncio.sleep(travel - REACTION + REACTION)
    result = (await client.post("/api/calibration/flink/mark", json={"mark": "arrived"})).json()
    result["started"] = started
    return result


# --- C1: measuring by watching ----------------------------------------------


async def test_c1_1_a_run_needs_an_end_stop(client) -> None:
    await park(client, 40)
    response = await client.post("/api/calibration/flink/run")
    assert response.status_code == 409
    assert response.json()["error"] == "not_at_end_stop"

    homing = (await client.post("/api/calibration/flink/home")).json()
    assert homing["measured"] is False
    assert (await client.get("/api/calibration/flink")).json()["runs"] == []


async def test_c1_2_two_presses_record_a_run(client) -> None:
    await park(client, 0)
    result = await guided_run(client)
    assert result["run"]["dead_seconds"] > 0
    assert result["run"]["total_seconds"] > result["run"]["dead_seconds"]
    assert result["run"]["rejected"] is None


async def test_c1_3_direction_alternates(client) -> None:
    await park(client, 0)
    first = await guided_run(client)
    assert first["started"]["direction"] == "up"
    second = await guided_run(client)
    assert second["started"]["direction"] == "down"
    assert second["started"]["from_percent"] == 100


async def test_c1_4_median_not_mean(client) -> None:
    """Three runs, one pressed very late. The stored value is the middle one."""
    await park(client, 0)
    await guided_run(client)  # up
    await guided_run(client)  # down
    await guided_run(client)  # up again

    body = (await client.get("/api/calibration/flink")).json()
    ups = [r["total_seconds"] for r in body["runs"] if r["direction"] == "up" and not r["rejected"]]
    assert len(ups) == 2
    assert body["up"]["travel_seconds"] == round(sum(sorted(ups)) / 2, 2)


async def test_c1_5_an_implausible_run_is_rejected_and_shown(client) -> None:
    await park(client, 0)
    await guided_run(client)

    # press "arrived" almost at once: a whole window crossed instantly
    await client.post("/api/calibration/flink/run")
    await client.post("/api/calibration/flink/mark", json={"mark": "moving"})
    result = (await client.post("/api/calibration/flink/mark", json={"mark": "arrived"})).json()

    assert result["run"]["rejected"] in {"too_short", "implausible"}
    runs = (await client.get("/api/calibration/flink")).json()["runs"]
    assert any(r["rejected"] for r in runs), "rejected runs stay visible with their reason"


async def test_c1_6_abandoning_and_the_timeout(client) -> None:
    """FR-008 and FR-009 — the second half of which was missing until T040."""
    await park(client, 0)
    await client.post("/api/calibration/flink/run")
    await asyncio.sleep(0.3)
    assert (await client.delete("/api/calibration/flink/run")).json()["aborted"] is True
    assert (await client.get("/api/shutters/flink")).json()["position"]["confidence"] != "certain"

    # And now a run nobody finishes at all. The timeout is twice the *expected*
    # travel, so an uncalibrated shutter waits twice the twenty-second default —
    # correct, and too slow for a test. Measure once first.
    await park(client, 0)
    await guided_run(client)
    await park(client, 0)
    await client.post("/api/calibration/flink/run")
    await asyncio.sleep(SIM_UP * 2 + 1.5)

    detail = (await client.get("/api/calibration/flink")).json()
    assert detail["active_run"] is None, "an unfinished run must not hold the shutter for ever"
    assert any(r["rejected"] == "abandoned" for r in detail["runs"])

    released = await client.post("/api/shutters/flink/command", json={"action": "close"})
    assert released.status_code == 200, "the shutter has to be usable again"


async def test_c1_7_the_measurement_takes_effect_at_once(client) -> None:
    await park(client, 0)
    await guided_run(client)

    await park(client, 0)
    body = (await client.post("/api/shutters/flink/command", json={"action": "open"})).json()
    from datetime import datetime

    duration = (
        datetime.fromisoformat(body["movement"]["expected_arrival"])
        - datetime.fromisoformat(body["movement"]["started_at"])
    ).total_seconds()
    assert duration < 5.0, "it must not still be animating on the twenty-second default"


async def test_c1_8_convergence_on_the_hidden_truth(client) -> None:
    """The scenario the whole feature stands on."""
    await park(client, 0)
    for _ in range(4):
        await guided_run(client)

    truth = (await client.get("/api/sim/truth")).json()["flink"]
    measured = (await client.get("/api/calibration/flink")).json()

    assert abs(measured["up"]["travel_seconds"] - truth["command_to_arrival_up"]) < 0.5
    assert abs(measured["down"]["travel_seconds"] - truth["command_to_arrival_down"]) < 0.5
    assert measured["up"]["travel_seconds"] > truth["command_to_arrival_up"], (
        "measured late, because a person presses late — not a bug"
    )


# --- C3: verification --------------------------------------------------------


async def test_c3_1_the_check_drives_to_the_displayed_midpoint(client) -> None:
    await park(client, 0)
    await guided_run(client)

    await park(client, 0)
    body = (await client.post("/api/calibration/flink/check")).json()
    assert body["target_percent"] == 50


async def test_c3_2_end_points_are_untouchable(client) -> None:
    await park(client, 0)
    await guided_run(client)
    for _ in range(6):
        await client.post("/api/calibration/flink/check")
        await client.post("/api/calibration/flink/check/answer", json={"answer": "too_high"})

    # The check drove down from the end of the guided run, so that is the
    # curve the answers bent — and the travel to test the end points on.
    await park(client, 100)
    await client.post("/api/shutters/flink/command", json={"action": "close"})
    tracker = client.app.state.tracker
    movement = tracker.movement("flink")
    a = client.app.state.calibration.curve_a("flink", "down")
    assert a != 1.0
    assert movement.curve_a == a
    assert movement.position_at(movement.started_monotonic) == 100
    assert movement.position_at(movement.started_monotonic + movement.duration_seconds) == 0


async def test_c3_3_undo_keeps_the_measurements(client) -> None:
    await park(client, 0)
    await guided_run(client)
    for _ in range(2):
        await client.post("/api/calibration/flink/check")
        await client.post("/api/calibration/flink/check/answer", json={"answer": "too_low"})

    before = (await client.get("/api/calibration/flink")).json()["up"]["travel_seconds"]
    after = (await client.delete("/api/calibration/flink/check")).json()
    assert after["up"]["curve_a"] == CURVE_NEUTRAL
    assert after["up"]["travel_seconds"] == before


async def test_c3_4_the_limit_is_reported(client) -> None:
    await park(client, 0)
    await guided_run(client)
    last = {}
    for _ in range(12):
        await client.post("/api/calibration/flink/check")
        last = (
            await client.post("/api/calibration/flink/check/answer", json={"answer": "too_low"})
        ).json()
    assert last["at_limit"] is True


async def test_c3_5_a_reversal_mid_window_waits_for_the_motor(client) -> None:
    """Found checking the down-curve: from a midpoint reached going down, the
    way back up was computed on the up-curve, the app declared arrival early,
    and the next command reached a motor that was still running."""
    await park(client, 100)
    await guided_run(client)  # down
    await guided_run(client)  # up
    for _ in range(4):
        await client.post("/api/calibration/flink/check")  # from 100 -> down
        await client.post("/api/calibration/flink/check/answer", json={"answer": "too_high"})
    sim = client.app.state.bridge._shutters["0x279631"]
    assert client.app.state.calibration.curve_a("flink", "down") != 1.0

    tracker = client.app.state.tracker

    async def motor_stopped() -> None:
        # The simulator steps once a second on its own; ask it directly instead of
        # guessing how long to sleep. Sleeping was what made this test flaky.
        for _ in range(200):
            sim.advance(time.monotonic())
            if sim.started_at is None:
                return
            await asyncio.sleep(0.05)
        raise AssertionError("the simulated motor never stopped")

    async def drive(**body) -> None:
        await motor_stopped()
        await client.post("/api/shutters/flink/command", json=body)
        movement = tracker.movement("flink")
        if movement is not None:
            await asyncio.sleep(movement.duration_seconds + 0.05)
        await tracker.tick()
        await motor_stopped()

    await drive(action="open")
    await drive(action="position", target_percent=50)  # down, on the bent curve
    await client.post(
        "/api/shutters/flink/command", json={"action": "position", "target_percent": 80}
    )
    sim.advance(time.monotonic())

    # The bridge runs for the change in its own counter; the app's duration is
    # the distance on the up-curve. They have to be the same distance.
    a_up = client.app.state.calibration.curve_a("flink", "up")
    distance = to_level(80, a_up) - to_level(50, a_up)
    assert sim.target_believed - sim.start_believed == pytest.approx(distance, abs=1.5)


async def test_the_simulated_house_stays_put_across_a_restart(tmp_path) -> None:
    """Otherwise every dev restart looks like somebody drove the shutters."""
    settings = Settings.model_validate(CONFIG)
    store = Store(tmp_path / "state.db")
    first = create_app(settings, store=store, bridge=SimBridge(addresses=["0x279631"]))
    await first.state.tracker._settle("flink", 100, first.state.tracker.position("flink").source)

    bridge = SimBridge(addresses=["0x279631"])
    bridge._shutters["0x279631"].percent = 0.0  # the simulator's own default
    create_app(settings, store=store, bridge=bridge)
    assert bridge.truth("0x279631") == 100


def test_a_command_to_where_the_bridge_already_counts_halts_the_motor() -> None:
    bridge = SimBridge(addresses=["0x279631"])
    shutter = bridge._shutters["0x279631"]
    shutter.command(0, now=100.0)  # from 100, down
    assert shutter.started_at is not None
    shutter.command(100, now=100.3)  # still in the dead time, counter still 100
    shutter.advance(130.0)
    assert bridge.truth("0x279631") == 100, "the close must not run on"
