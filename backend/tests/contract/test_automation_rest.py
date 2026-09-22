"""Automations over REST match contracts/rest.md (feature 003)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG

WEEKDAYS = [True] * 5 + [False] * 2


@pytest.fixture
def client(tmp_path):
    settings = Settings.model_validate(CONFIG)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    with TestClient(app) as c:
        yield c


def body(**over) -> dict:
    b = {
        "name": "Werktags morgens",
        "days": WEEKDAYS,
        "trigger": {"kind": "time", "time": "06:45"},
        "targets": "all",
        "action": {"kind": "open"},
    }
    b.update(over)
    return b


# --- US1 ---------------------------------------------------------------------


def test_list_shape(client) -> None:
    got = client.get("/api/automations").json()
    assert set(got) == {"rules", "pause", "clock", "location"}
    assert got["rules"] == []
    assert got["pause"] == {"paused": False, "until": None}
    assert got["clock"]["reliable"] in (True, False)
    assert got["location"] is None


def test_create_returns_the_stored_rule(client) -> None:
    response = client.post("/api/automations", json=body())
    assert response.status_code == 201
    rule = response.json()
    assert rule["id"].startswith("r_")
    assert rule["name"] == "Werktags morgens"
    assert rule["days"] == WEEKDAYS
    assert rule["trigger"] == {"kind": "time", "time": "06:45"}
    assert rule["targets"] == "all"
    assert rule["action"] == {"kind": "open", "percent": None}
    assert rule["enabled"] is True and rule["skip_next"] is False
    assert rule["next"]["at"] is not None and rule["next"]["reason"] is None
    assert rule["last"] is None
    assert rule["conflicts"] == []
    assert [r["id"] for r in client.get("/api/automations").json()["rules"]] == [rule["id"]]


@pytest.mark.parametrize(
    "over",
    [
        {"targets": ["gibtsnicht"]},
        {"targets": []},
        {"action": {"kind": "position"}},
        {"trigger": {"kind": "time", "time": "06:45", "offset_minutes": 10}},
        {"trigger": {"kind": "time", "time": "6:45"}},
        {"name": ""},
        {"days": [True] * 6},
    ],
)
def test_invalid_rules_are_422_in_the_common_error_shape(client, over) -> None:
    response = client.post("/api/automations", json=body(**over))
    assert response.status_code == 422
    assert set(response.json()) == {"error", "message", "detail"}


def test_delete_is_204_and_gone(client) -> None:
    rule = client.post("/api/automations", json=body()).json()
    assert client.delete(f"/api/automations/{rule['id']}").status_code == 204
    assert client.get("/api/automations").json()["rules"] == []
    assert client.delete(f"/api/automations/{rule['id']}").status_code == 404


def test_every_change_tells_open_clients(client) -> None:
    with client.websocket_connect("/api/ws") as socket:
        socket.receive_json()  # snapshot
        rule = client.post("/api/automations", json=body()).json()
        assert socket.receive_json()["type"] == "rules_changed"
        client.delete(f"/api/automations/{rule['id']}")
        assert socket.receive_json()["type"] == "rules_changed"
