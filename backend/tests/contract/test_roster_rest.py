"""Feature 005: the roster REST surface matches specs/005-shutter-add-remove/contracts/rest.md."""

from __future__ import annotations

import asyncio

import pytest

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings

ERROR_KEYS = {"error", "message", "detail"}
EXTRA = {"0x279630": "Bad", "0x279631": "Gästezimmer", "0x279632": "Küche"}


@pytest.fixture
def bridge(app_settings: Settings) -> SimBridge:
    """A bridge that knows the three configured shutters and three more."""
    names = {s.address: s.name for s in app_settings.shutter} | EXTRA
    return SimBridge(addresses=list(names), names=names)


async def announced(client, count: int) -> list[dict]:
    """Wait until the retained announcements have gone through the pump."""
    for _ in range(100):
        body = (await client.get("/api/roster")).json()
        if len(body["new"]) >= count:
            return body["new"]
        await asyncio.sleep(0.01)
    raise AssertionError(f"expected {count} new shutters, got {body['new']}")


async def confirm(client, address: str, name: str) -> dict:
    response = await client.post(f"/api/roster/new/{address}", json={"name": name})
    assert response.status_code == 201, response.json()
    return response.json()


# --- US1 ----------------------------------------------------------------------


async def test_roster_shape(client) -> None:
    await announced(client, 3)
    body = (await client.get("/api/roster")).json()
    assert set(body) == {"active", "new", "set_aside", "bridge"}
    assert [e["id"] for e in body["active"]] == ["wohnzimmer", "kueche", "schlafzimmer"]
    assert body["active"][0] == {
        "id": "wohnzimmer",
        "name": "Wohnzimmer",
        "address": "0x279621",
        "origin": "config",
        "forgotten": False,
        "removable": False,
    }
    assert body["new"] == [
        {"address": "0x279630", "bridge_name": "Bad", "suggested_name": "Bad"},
        {"address": "0x279631", "bridge_name": "Gästezimmer", "suggested_name": "Gästezimmer"},
        {"address": "0x279632", "bridge_name": "Küche", "suggested_name": "Küche 2"},
    ]
    assert body["set_aside"] == []
    assert body["bridge"] == {"announcements_seen": True, "web_url": None}


async def test_confirm_returns_the_shutter(client) -> None:
    await announced(client, 3)
    shutter = await confirm(client, "0x279631", "  Gästezimmer ")
    assert shutter["id"] == "gaestezimmer"
    assert shutter["name"] == "Gästezimmer"
    assert shutter["origin"] == "bridge"
    assert shutter["forgotten"] is False
    assert shutter["calibrated"] is False
    assert shutter["position"]["confidence"] == "unknown"
    assert (await client.get("/api/shutters/gaestezimmer")).status_code == 200
    body = (await client.get("/api/roster")).json()
    assert "0x279631" not in [n["address"] for n in body["new"]]
    assert body["active"][-1]["removable"] is True


async def test_confirm_name_taken(client) -> None:
    await announced(client, 3)
    response = await client.post("/api/roster/new/0x279632", json={"name": "küche"})
    assert response.status_code == 409
    body = response.json()
    assert set(body) == ERROR_KEYS
    assert body["error"] == "name_taken"


async def test_confirm_not_announced(client) -> None:
    await announced(client, 3)
    for address in ("0x279699", "0x279621"):
        response = await client.post(f"/api/roster/new/{address}", json={"name": "X"})
        assert response.status_code == 404
        assert response.json()["error"] == "not_announced"


@pytest.mark.parametrize("name", ["", "   ", "x" * 41])
async def test_confirm_name_length(client, name: str) -> None:
    await announced(client, 3)
    response = await client.post("/api/roster/new/0x279630", json={"name": name})
    assert response.status_code == 422


async def test_rename_keeps_the_id(client) -> None:
    await announced(client, 3)
    await confirm(client, "0x279630", "Bad")
    response = await client.patch("/api/shutters/bad", json={"name": "Badezimmer"})
    assert response.status_code == 200
    assert (response.json()["id"], response.json()["name"]) == ("bad", "Badezimmer")
    assert (await client.get("/api/shutters/bad")).json()["name"] == "Badezimmer"


async def test_rename_name_taken(client) -> None:
    await announced(client, 3)
    await confirm(client, "0x279630", "Bad")
    response = await client.patch("/api/shutters/bad", json={"name": "Wohnzimmer"})
    assert response.status_code == 409
    assert response.json()["error"] == "name_taken"


async def test_rename_configured_by_hand(client) -> None:
    response = await client.patch("/api/shutters/wohnzimmer", json={"name": "Wohnen"})
    assert response.status_code == 409
    body = response.json()
    assert set(body) == ERROR_KEYS
    assert body["error"] == "configured_by_hand"


async def test_rename_unknown(client) -> None:
    response = await client.patch("/api/shutters/nope", json={"name": "X"})
    assert response.status_code == 404


async def test_configured_web_url_wins(client) -> None:
    client.app.state.settings.bridge.web_url = "http://pi-somfy.fritz.box/"
    body = (await client.get("/api/roster")).json()
    assert body["bridge"]["web_url"] == "http://pi-somfy.fritz.box/"
