"""T036 / quickstart C4.1: calibrating a shutter must not make its position known.

This is the one way feature 002 could damage feature 001's central promise. Six
good runs feel like certainty, and mid-travel the position is still dead
reckoning that drifts the moment anything unobserved happens.

Walked by eye in the quickstart as well — a screen can imply certainty through
wording or colour without any field here changing. What this file holds is the
part a machine can check: the server never claims it.
"""

from __future__ import annotations

import asyncio

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.models import Direction, MeasurementRun, RunKind, utcnow
from somfy_shutters.store import Store

CONFIG = {
    "general": {"default_travel_seconds": 2, "stale_after_hours": 12},
    "bridge": {"kind": "sim"},
    "shutter": [{"id": "flink", "name": "Flink", "address": "0x279631"}],
}


@pytest_asyncio.fixture
async def client(tmp_path):
    settings = Settings.model_validate(CONFIG)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    for shutter in bridge._shutters.values():
        shutter.dead_time = 0.1
        shutter.travel_up = 1.0
        shutter.travel_down = 0.8
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    # fully calibrated, in both directions, on plenty of runs
    for direction, total in ((Direction.UP, 2.0), (Direction.DOWN, 1.8)):
        for _ in range(3):
            app.state.calibration.record(
                MeasurementRun(
                    shutter_id="flink",
                    direction=direction,
                    dead_seconds=0.1,
                    total_seconds=total,
                    kind=RunKind.GUIDED,
                    recorded_at=utcnow(),
                )
            )
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        http.app = app  # type: ignore[attr-defined]
        yield http


async def drive_to(client, target: int) -> dict:
    await client.post(
        "/api/shutters/flink/command", json={"action": "position", "target_percent": target}
    )
    await asyncio.sleep(2.6)
    return (await client.get("/api/shutters/flink")).json()


async def test_the_shutter_really_is_calibrated(client) -> None:
    """Otherwise the rest of this file proves nothing."""
    body = (await client.get("/api/calibration/flink")).json()
    assert body["state"] == "calibrated"
    assert body["up"]["runs"] == 3
    assert body["down"]["runs"] == 3


async def test_mid_travel_is_still_an_estimate(client) -> None:
    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": 0})
    body = await drive_to(client, 50)

    position = body["position"]
    assert position["percent"] == 50
    assert position["confidence"] == "estimated", "calibration improves the guess, not the knowing"


async def test_the_estimate_still_carries_its_age(client) -> None:
    """FR-007: the number alone is not enough, and calibration does not change that."""
    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": 0})
    body = await drive_to(client, 50)

    position = body["position"]
    assert position["certain_at"] is not None
    assert position["age_seconds"] is not None
    assert position["age_seconds"] >= 0


async def test_the_certainty_clock_still_points_at_the_last_end_stop(client) -> None:
    """Not at the moment of calibration, and not at the last movement."""
    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": 0})
    at_end_stop = (await client.get("/api/shutters/flink")).json()["position"]
    assert at_end_stop["confidence"] == "certain"

    body = await drive_to(client, 50)
    assert body["position"]["certain_at"] == at_end_stop["certain_at"]


async def test_a_calibrated_estimate_goes_stale_like_any_other(client) -> None:
    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": 0})
    await drive_to(client, 50)

    # pretend twelve hours passed since the last end stop
    tracker = client.app.state.tracker
    position = tracker.position("flink")
    assert position.is_stale(stale_after_hours=0.0) is True, (
        "a measured travel time does not stop an estimate from aging"
    )


async def test_only_an_end_stop_makes_it_certain_again(client) -> None:
    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": 0})
    await drive_to(client, 50)
    assert (await client.get("/api/shutters/flink")).json()["position"]["confidence"] == "estimated"

    body = await drive_to(client, 100)
    assert body["position"]["confidence"] == "certain"


async def test_no_endpoint_ever_returns_a_percent_without_a_confidence(client) -> None:
    """The invariant behind all of the above, checked on the wire."""
    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": 0})
    await drive_to(client, 50)

    for path in ("/api/shutters", "/api/shutters/flink"):
        payload = (await client.get(path)).json()
        shutters = payload.get("shutters", [payload])
        for shutter in shutters:
            position = shutter["position"]
            assert "confidence" in position
            assert position["confidence"] in {"certain", "estimated", "unknown"}
