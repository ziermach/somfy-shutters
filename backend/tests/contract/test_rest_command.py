"""T018: the REST surface matches contracts/rest.md."""

from __future__ import annotations

SHUTTER_KEYS = {
    "id",
    "name",
    "calibrated",
    "travel_up_seconds",
    "travel_down_seconds",
    "position",
    "movement",
    "measuring",
}
POSITION_KEYS = {"percent", "confidence", "certain_at", "age_seconds", "stale", "source"}
MOVEMENT_KEYS = {
    "from_percent",
    "target_percent",
    "direction",
    "started_at",
    "expected_arrival",
    "origin",
    "curve_a",
}


async def test_list_shape(client) -> None:
    body = (await client.get("/api/shutters")).json()
    assert set(body) == {"shutters", "bridge"}
    assert set(body["bridge"]) == {"connected", "kind"}
    assert len(body["shutters"]) == 3
    for shutter in body["shutters"]:
        assert set(shutter) == SHUTTER_KEYS
        assert set(shutter["position"]) == POSITION_KEYS


async def test_every_position_carries_its_confidence(client) -> None:
    """FR-011 at the wire level: no bare number ever leaves the server."""
    body = (await client.get("/api/shutters")).json()
    for shutter in body["shutters"]:
        assert shutter["position"]["confidence"] in {"certain", "estimated", "unknown"}


async def test_command_returns_a_movement(client) -> None:
    response = await client.post("/api/shutters/wohnzimmer/command", json={"action": "close"})
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert set(body["movement"]) == MOVEMENT_KEYS
    assert body["movement"]["direction"] == "down"
    assert body["movement"]["target_percent"] == 0


async def test_stop_returns_no_movement(client) -> None:
    await client.post("/api/shutters/wohnzimmer/command", json={"action": "close"})
    body = (await client.post("/api/shutters/wohnzimmer/command", json={"action": "stop"})).json()
    assert body == {"accepted": True, "movement": None}


async def test_unknown_shutter_is_404_with_the_shared_error_shape(client) -> None:
    response = await client.post("/api/shutters/keller/command", json={"action": "open"})
    assert response.status_code == 404
    assert set(response.json()) == {"error", "message", "detail"}
    assert response.json()["error"] == "unknown_shutter"


async def test_unknown_action_is_422(client) -> None:
    response = await client.post("/api/shutters/wohnzimmer/command", json={"action": "wobble"})
    assert response.status_code == 422


async def test_position_without_target_is_422(client) -> None:
    response = await client.post("/api/shutters/wohnzimmer/command", json={"action": "position"})
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "target_required"


async def test_out_of_range_target_is_422(client) -> None:
    response = await client.post(
        "/api/shutters/wohnzimmer/command", json={"action": "position", "target_percent": 140}
    )
    assert response.status_code == 422


async def test_command_all_reports_per_shutter(client) -> None:
    response = await client.post("/api/shutters/command", json={"action": "open"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert {r["id"] for r in results} == {"wohnzimmer", "kueche", "schlafzimmer"}
    assert all(r["accepted"] for r in results)


async def test_command_all_carries_movements_and_needs_a_target_for_position(client) -> None:
    """Feature 004, T004: "Alle" now goes through apply_many."""
    response = await client.post("/api/shutters/command", json={"action": "close"})
    assert all(set(r["movement"]) == MOVEMENT_KEYS for r in response.json()["results"])
    response = await client.post("/api/shutters/command", json={"action": "position"})
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "target_required"


async def test_resync_says_which_end_stop(client) -> None:
    body = (await client.post("/api/shutters/wohnzimmer/resync")).json()
    assert body["accepted"] is True
    assert body["target_percent"] in (0, 100)


async def test_health_stays_ok_when_the_bridge_is_down(client) -> None:
    await client.post("/api/sim/bridge/offline")
    body = (await client.get("/api/health")).json()
    assert body["status"] == "ok"
    assert body["bridge"]["connected"] is False
    assert body["shutters"] == 3
