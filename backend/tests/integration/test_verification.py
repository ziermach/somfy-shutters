"""T031: the check that corrects the middle of a travel without touching its ends."""

from __future__ import annotations

import asyncio

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.calibration import CURVE_MAX, CURVE_MIN, CURVE_NEUTRAL, CURVE_STEP
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.models import Direction, MeasurementRun, RunKind, utcnow
from somfy_shutters.store import Store

CONFIG = {
    "general": {"default_travel_seconds": 20, "stale_after_hours": 12},
    "bridge": {"kind": "sim"},
    "shutter": [{"id": "flink", "name": "Flink", "address": "0x279631"}],
}


@pytest_asyncio.fixture
async def client(tmp_path):
    settings = Settings.model_validate(CONFIG)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    for shutter in bridge._shutters.values():
        shutter.dead_time = 0.05
        shutter.travel_up = 1.0
        shutter.travel_down = 0.9
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        http.app = app  # type: ignore[attr-defined]
        yield http


def calibrate(app, direction: Direction = Direction.UP, total: float = 1.0) -> None:
    for _ in range(3):
        app.state.calibration.record(
            MeasurementRun(
                shutter_id="flink",
                direction=direction,
                dead_seconds=0.6,
                total_seconds=total,
                kind=RunKind.GUIDED,
                recorded_at=utcnow(),
            )
        )


async def answer(client, reply: str) -> dict:
    response = await client.post("/api/calibration/flink/check/answer", json={"answer": reply})
    return response.json()


async def test_a_check_needs_something_to_check(client) -> None:
    response = await client.post("/api/calibration/flink/check")
    assert response.status_code == 409
    assert response.json()["error"] == "not_calibrated"


async def test_the_check_drives_to_the_displayed_midpoint(client) -> None:
    calibrate(client.app)
    body = (await client.post("/api/calibration/flink/check")).json()
    assert body["accepted"] is True
    assert body["target_percent"] == 50


async def test_answers_move_the_curve_in_the_direction_reported(client) -> None:
    calibrate(client.app)
    lower = await answer(client, "too_high")
    assert lower["curve_a"] == CURVE_NEUTRAL - CURVE_STEP
    assert lower["shift_pp"] > 1.0

    back = await answer(client, "too_low")
    assert back["curve_a"] == CURVE_NEUTRAL


async def test_about_right_changes_nothing(client) -> None:
    calibrate(client.app)
    assert (await answer(client, "about_right"))["curve_a"] == CURVE_NEUTRAL


async def test_the_bounds_are_reported(client) -> None:
    """Each direction has its own limit, and the response says when it is reached."""
    calibrate(client.app)
    last = {}
    for _ in range(20):
        last = await answer(client, "too_low")
    assert last["curve_a"] == CURVE_MAX
    assert last["at_limit"] is True

    for _ in range(40):
        last = await answer(client, "too_high")
    assert last["curve_a"] == CURVE_MIN
    assert last["at_limit"] is True


async def test_undo_restores_the_curve_and_keeps_the_measurements(client) -> None:
    """FR-026: verification is reversible on its own."""
    calibrate(client.app)
    for _ in range(3):
        await answer(client, "too_high")
    before = (await client.get("/api/calibration/flink")).json()
    assert before["up"]["curve_a"] != CURVE_NEUTRAL
    assert before["up"]["runs"] == 3

    after = (await client.delete("/api/calibration/flink/check")).json()
    assert after["up"]["curve_a"] == CURVE_NEUTRAL
    assert after["up"]["runs"] == 3, "the measurements must survive an undo"
    assert after["up"]["travel_seconds"] == 1.0


async def test_the_end_points_are_untouched_by_any_number_of_answers(client) -> None:
    """FR-025, through the real API: the display still reaches exactly 0 and 100."""
    calibrate(client.app)
    for _ in range(6):
        await answer(client, "too_high")

    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": 0})
    await client.post("/api/shutters/flink/command", json={"action": "open"})

    tracker = client.app.state.tracker
    movement = tracker.movement("flink")
    a = client.app.state.calibration.curve_a("flink", Direction.UP)
    assert a != 1.0, "the curve is actually bent for this assertion to mean anything"
    assert movement.position_at(movement.started_monotonic, curve_a=a) == 0
    assert (
        movement.position_at(movement.started_monotonic + movement.duration_seconds, curve_a=a)
        == 100
    )


async def test_a_check_cannot_start_during_a_measurement(client) -> None:
    calibrate(client.app)
    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": 0})
    await client.post("/api/calibration/flink/run")
    response = await client.post("/api/calibration/flink/check")
    assert response.status_code == 409
    assert response.json()["error"] == "already_running"
    await client.delete("/api/calibration/flink/run")


async def test_the_check_actually_closes_the_gap(client) -> None:
    """The scenario the whole of User Story 3 exists for.

    Two earlier versions passed every other test in this file while being unable
    to move the shutter one millimetre: first because the curve family was
    antisymmetric about the midpoint, then because the curve only reshaped the
    animation and never the command. This drives to the middle, asks what a
    person would see, and insists the gap closes.
    """
    calibrate(client.app)
    bridge = client.app.state.bridge
    address = client.app.state.settings.shutters["flink"].address
    bridge._shutters[address].curve_a = 1.34  # the window's own shape, unknown to the app

    async def to_middle() -> tuple[int, float]:
        await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": 0})
        bridge.place(address, 0.0)
        await client.post(
            "/api/shutters/flink/command", json={"action": "position", "target_percent": 50}
        )
        for _ in range(200):
            body = (await client.get("/api/shutters/flink")).json()
            if body["movement"] is None:
                break
            await asyncio.sleep(0.1)
        # The app settles on its own clock; the simulated window only advances
        # when the bridge's loop ticks, so give it one before reading the truth.
        await asyncio.sleep(1.2)
        return body["position"]["percent"], bridge.truth(address)

    shown, real = await to_middle()
    first_gap = abs(shown - real)
    assert first_gap > 5, "the simulated window has to be off, or this proves nothing"

    for _ in range(6):
        # the person reports the shutter: higher than the mark, or lower
        reply = "too_high" if real > shown else "too_low"
        await answer(client, reply)
        shown, real = await to_middle()

    assert abs(shown - real) < 2.0, f"still {shown - real:+.1f} pp out after six answers"
    assert abs(shown - real) < first_gap
