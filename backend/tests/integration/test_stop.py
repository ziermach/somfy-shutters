"""Feature 006, US2: stop actually stops, through the explicit STOP.

On current Pi-Somfy a position equal to its own belief does nothing — the old way of
stopping ("go to where you are") would let the shutter run on. Against the simulator,
which behaves the same, a stop must halt the motor.
"""

from __future__ import annotations

import asyncio

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.models import Confidence
from somfy_shutters.store import Store

CONFIG = {
    "general": {"default_travel_seconds": 4},
    "bridge": {"kind": "sim"},
    "shutter": [
        {
            "id": "flink",
            "name": "Flink",
            "address": "0x279631",
            "travel_up_seconds": 4.0,
            "travel_down_seconds": 4.0,
        }
    ],
}
ADDRESS = "0x279631"


@pytest_asyncio.fixture
async def client(tmp_path):
    settings = Settings.model_validate(CONFIG)
    bridge = SimBridge(addresses=[ADDRESS])
    for shutter in bridge._shutters.values():
        shutter.dead_time = 0.1
        shutter.travel_up = 4.0
        shutter.travel_down = 4.0
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        http.app = app  # type: ignore[attr-defined]
        http.bridge = bridge  # type: ignore[attr-defined]
        yield http


async def test_stop_halfway_halts_the_motor(client) -> None:
    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": 100})
    await client.post("/api/shutters/flink/command", json={"action": "close"})
    await asyncio.sleep(1.6)
    sent = await client.post("/api/shutters/flink/command", json={"action": "stop"})
    assert sent.status_code == 200

    halted = client.bridge.truth(ADDRESS)
    await asyncio.sleep(2.0)
    import time

    client.bridge._shutters[ADDRESS].advance(time.monotonic())
    assert client.bridge.truth(ADDRESS) == halted, "the motor must not run on"
    assert 20 < halted < 90

    position = (await client.get("/api/shutters/flink")).json()["position"]
    assert position["confidence"] == Confidence.ESTIMATED.value
    assert abs(position["percent"] - halted) < 15


async def test_aborting_a_calibration_run_halts_the_same_way(client) -> None:
    client.bridge.place(ADDRESS, 0.0)  # the motor, not just the app, starts at the bottom
    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": 0})
    started = await client.post("/api/calibration/flink/run")
    assert started.status_code == 200
    await asyncio.sleep(1.6)
    await client.delete("/api/calibration/flink/run")

    halted = client.bridge.truth(ADDRESS)
    await asyncio.sleep(2.0)
    import time

    client.bridge._shutters[ADDRESS].advance(time.monotonic())
    assert client.bridge.truth(ADDRESS) == halted
    assert 10 < halted < 95
