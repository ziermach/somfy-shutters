"""T019 and T047: the WebSocket matches contracts/websocket.md.

Driven with the synchronous TestClient, because the ASGI transport used by the
other contract tests cannot open a socket.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG


@pytest.fixture
def test_client(tmp_path):
    settings = Settings.model_validate(CONFIG)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    with TestClient(app) as client:
        client.bridge = bridge  # type: ignore[attr-defined]
        yield client


def test_first_frame_is_always_a_full_snapshot(test_client) -> None:
    """FR-020. No resume-from-offset: every connect gets everything."""
    with test_client.websocket_connect("/api/ws") as socket:
        frame = socket.receive_json()
    assert frame["type"] == "snapshot"
    assert frame["seq"] == 1
    assert set(frame["data"]) == {"shutters", "bridge"}
    assert len(frame["data"]["shutters"]) == 3


def test_a_reconnect_gets_a_snapshot_too(test_client) -> None:
    with test_client.websocket_connect("/api/ws") as socket:
        assert socket.receive_json()["type"] == "snapshot"
    with test_client.websocket_connect("/api/ws") as socket:
        second = socket.receive_json()
    assert second["type"] == "snapshot"
    assert second["seq"] > 1, "seq keeps counting across connections"


def test_movement_frame_shape(test_client) -> None:
    with test_client.websocket_connect("/api/ws") as socket:
        socket.receive_json()  # snapshot
        test_client.post("/api/shutters/wohnzimmer/command", json={"action": "close"})
        frame = socket.receive_json()

    assert frame["type"] == "movement"
    assert frame["shutter_id"] == "wohnzimmer"
    assert set(frame["movement"]) == {
        "from_percent",
        "target_percent",
        "direction",
        "started_at",
        "expected_arrival",
        "origin",
        "curve_a",
    }
    assert frame["movement"]["origin"] == "local"


def test_seq_increases_monotonically(test_client) -> None:
    with test_client.websocket_connect("/api/ws") as socket:
        seqs = [socket.receive_json()["seq"]]
        for action in ("close", "open"):
            test_client.post("/api/shutters/kueche/command", json={"action": action})
            seqs.append(socket.receive_json()["seq"])
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


def test_correction_frame_carries_ease(test_client) -> None:
    """FR-017 on the wire: the client is told to glide, not to teleport.

    The shutter has to be idle for a report to win at all — while one of our
    commands is travelling, reports are ignored by design, which is what an
    earlier version of this test accidentally asserted.
    """
    with test_client.websocket_connect("/api/ws") as socket:
        socket.receive_json()  # snapshot

        # Idle at a known end stop, established by a report rather than a command.
        test_client.post("/api/sim/report", json={"shutter_id": "wohnzimmer", "percent": 0})
        assert socket.receive_json()["type"] == "position"

        test_client.post("/api/sim/report", json={"shutter_id": "wohnzimmer", "percent": 40})
        frame = socket.receive_json()

    assert frame["type"] == "correction"
    assert frame["ease_ms"] == 400
    assert frame["position"]["confidence"] == "estimated"
    assert frame["position"]["percent"] == 40


def test_bridge_frame_is_sent_on_transition(test_client) -> None:
    with test_client.websocket_connect("/api/ws") as socket:
        socket.receive_json()  # snapshot
        test_client.post("/api/sim/bridge/offline")
        frame = socket.receive_json()

    assert frame == {"type": "bridge", "connected": False, "kind": "sim", "seq": frame["seq"]}


def test_every_client_sees_the_movement(test_client) -> None:
    """FR-018: whoever caused it, everyone animates from the same timestamps."""
    with (
        test_client.websocket_connect("/api/ws") as first,
        test_client.websocket_connect("/api/ws") as second,
    ):
        first.receive_json()
        second.receive_json()
        test_client.post("/api/shutters/wohnzimmer/command", json={"action": "close"})
        a = first.receive_json()
        b = second.receive_json()

    assert a["movement"] == b["movement"]


def test_a_measurement_announces_itself_to_every_client(test_client) -> None:
    """Open clients have to stop offering buttons the server would refuse."""
    test_client.post("/api/sim/report", json={"shutter_id": "kueche", "percent": 0})
    with test_client.websocket_connect("/api/ws") as socket:
        socket.receive_json()  # snapshot

        test_client.post("/api/calibration/kueche/run")
        frames = [socket.receive_json() for _ in range(2)]
        started = next(f for f in frames if f["type"] == "measuring")
        assert started["shutter_id"] == "kueche"
        assert started["active"] is True

        test_client.delete("/api/calibration/kueche/run")
        ended = None
        for _ in range(4):
            frame = socket.receive_json()
            if frame["type"] == "measuring":
                ended = frame
                break
        assert ended is not None and ended["active"] is False
