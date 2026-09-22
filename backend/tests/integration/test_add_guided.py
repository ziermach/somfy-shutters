"""Feature 005, US2 / quickstart A2: adding a shutter, as the guide walks through it.

FR-008 / SC-003: an open guide sees the new shutter within 5 s of the bridge announcing it.
"""

from __future__ import annotations

import asyncio
import time

from fastapi.testclient import TestClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG


def make_client(tmp_path) -> TestClient:
    settings = Settings.model_validate(CONFIG)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    return TestClient(create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge))


def test_an_open_guide_hears_of_the_new_shutter_within_five_seconds(tmp_path) -> None:
    with make_client(tmp_path) as client, client.websocket_connect("/api/ws") as socket:
        snapshot = socket.receive_json()
        assert snapshot["data"]["roster"] == {"new": 0, "forgotten": []}
        client.post("/api/sim/bridge/shutters", json={"name": "Bad"})
        started = time.monotonic()
        client.post("/api/sim/bridge/restart")
        while True:
            frame = socket.receive_json()
            if frame["type"] == "roster" and frame["new"] == 1:
                break
            assert time.monotonic() - started < 5, "no roster frame within 5 s"
        assert time.monotonic() - started < 5
        [new] = client.get("/api/roster").json()["new"]
        assert new["bridge_name"] == "Bad"


def test_confirming_sends_a_fresh_snapshot_to_every_client(tmp_path) -> None:
    with make_client(tmp_path) as client, client.websocket_connect("/api/ws") as socket:
        socket.receive_json()
        address = client.post("/api/sim/bridge/shutters", json={"name": "Bad"}).json()["address"]
        client.post("/api/sim/bridge/restart")
        for _ in range(100):
            if client.get("/api/roster").json()["new"]:
                break
            time.sleep(0.01)
        response = client.post(f"/api/roster/new/{address}", json={"name": "Bad"})
        assert response.status_code == 201
        while True:
            frame = socket.receive_json()
            if frame["type"] == "snapshot":
                break
        assert "bad" in [s["id"] for s in frame["data"]["shutters"]]


async def test_two_added_before_one_restart_are_both_found(tmp_path) -> None:
    from httpx import ASGITransport, AsyncClient

    settings = Settings.model_validate(CONFIG)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        await http.post("/api/sim/bridge/shutters", json={"name": "Bad"})
        await http.post("/api/sim/bridge/shutters", json={"name": "Bad oben"})
        await http.post("/api/sim/bridge/restart")
        for _ in range(100):
            if len((await http.get("/api/roster")).json()["new"]) == 2:
                break
            await asyncio.sleep(0.01)
        names = [n["bridge_name"] for n in (await http.get("/api/roster")).json()["new"]]
        assert names == ["Bad", "Bad oben"]


async def test_the_bridge_ignores_a_new_shutter_until_it_restarts() -> None:
    """Pi-Somfy subscribes to a shutter's commands only when it connects to the broker."""
    bridge = SimBridge(addresses=["0x279621"])
    address = bridge.bridge_add("Bad")
    bridge.place(address, 100)
    await bridge.send_level(address, 0)
    assert not bridge._shutters[address].moving
    bridge.bridge_restart()
    await bridge.send_level(address, 0)
    assert bridge._shutters[address].moving
