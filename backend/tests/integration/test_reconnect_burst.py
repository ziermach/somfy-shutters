"""Feature 006, SC-004: the broker's replay on connect is old news, not movement."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG


def test_a_restart_with_known_positions_produces_no_correction(tmp_path) -> None:
    settings = Settings.model_validate(CONFIG)
    db = tmp_path / "state.db"

    first = create_app(
        settings, store=Store(db), bridge=SimBridge(addresses=[s.address for s in settings.shutter])
    )
    with TestClient(first) as client:
        for sid, pct in (("wohnzimmer", 100), ("kueche", 0), ("schlafzimmer", 100)):
            client.post("/api/sim/report", json={"shutter_id": sid, "percent": pct})
        known = {
            s["id"]: s["position"]["percent"]
            for s in client.get("/api/shutters").json()["shutters"]
        }

    # Same house, new process: the simulator replays every position as retained.
    second = create_app(
        settings, store=Store(db), bridge=SimBridge(addresses=[s.address for s in settings.shutter])
    )
    with TestClient(second) as client, client.websocket_connect("/api/ws") as socket:
        socket.receive_json()  # snapshot
        client.portal.call(asyncio.sleep, 0.5)  # let the burst be processed
        client.post("/api/sim/bridge/offline")  # a frame we know will come, to end the read
        frames = []
        while True:
            frame = socket.receive_json()
            frames.append(frame)
            if frame["type"] == "bridge":
                break
        after = {
            s["id"]: s["position"]["percent"]
            for s in client.get("/api/shutters").json()["shutters"]
        }

    assert [f for f in frames if f["type"] in ("correction", "movement")] == []
    assert after == known
