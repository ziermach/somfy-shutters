"""Feature 006: POST /api/sim/movement injects a live movement report."""

from __future__ import annotations

from fastapi.testclient import TestClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG


def test_movement_injection(tmp_path) -> None:
    settings = Settings.model_validate(CONFIG)
    app = create_app(
        settings,
        store=Store(tmp_path / "s.db"),
        bridge=SimBridge(addresses=[s.address for s in settings.shutter]),
    )
    with TestClient(app) as client:
        client.post("/api/sim/report", json={"shutter_id": "kueche", "percent": 0})
        got = client.post("/api/sim/movement", json={"shutter_id": "kueche", "state": "opening"})
        assert got.status_code == 200 and got.json()["position"]["confidence"] == "estimated"
        assert (
            client.post(
                "/api/sim/movement", json={"shutter_id": "kueche", "state": "dancing"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/sim/movement", json={"shutter_id": "nope", "state": "opening"}
            ).status_code
            == 404
        )
