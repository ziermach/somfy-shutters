"""Feature 005: the simulator's model of the bridge's own interface (contracts/rest.md)."""

from __future__ import annotations

import asyncio

from httpx import ASGITransport, AsyncClient

from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG


async def new_addresses(client) -> list[str]:
    return [n["address"] for n in (await client.get("/api/roster")).json()["new"]]


async def test_added_in_the_bridge_is_not_announced_before_a_restart(client) -> None:
    response = await client.post("/api/sim/bridge/shutters", json={"name": "Bad"})
    assert response.status_code == 201
    body = response.json()
    assert body == {"address": "0x279624", "name": "Bad", "announced": False}
    await asyncio.sleep(0.05)
    assert await new_addresses(client) == []
    listed = (await client.get("/api/sim/bridge/shutters")).json()["shutters"]
    assert {"address": "0x279624", "name": "Bad", "enabled": True, "listening": False} in listed


async def test_restart_announces_live(client) -> None:
    seen: list[dict] = []

    async def listen(event: dict) -> None:
        if event.get("type") in ("bridge", "roster"):
            seen.append(event)

    client.app.state.bus.subscribe(listen)
    await client.post("/api/sim/bridge/shutters", json={"name": "Bad"})
    response = await client.post("/api/sim/bridge/restart")
    assert response.status_code == 200
    assert response.json() == {"connected": True}
    for _ in range(100):
        if await new_addresses(client) == ["0x279624"]:
            break
        await asyncio.sleep(0.01)
    assert await new_addresses(client) == ["0x279624"]
    assert [e["connected"] for e in seen if e["type"] == "bridge"][-2:] == [False, True]


async def test_delete_keeps_the_retained_announcement(client) -> None:
    bridge = client.app.state.bridge
    assert (await client.delete("/api/sim/bridge/shutters/0x279623")).status_code == 204
    assert "0x279623" in bridge._retained_announcements
    assert (await client.delete("/api/sim/bridge/shutters/0x279623")).status_code == 404
    assert (await client.delete("/api/sim/bridge/shutters/0x279699")).status_code == 404


async def test_the_old_online_offline_route_still_works(client) -> None:
    assert (await client.post("/api/sim/bridge/offline")).json() == {"connected": False}
    assert (await client.post("/api/sim/bridge/online")).json() == {"connected": True}


async def test_sim_routes_do_not_exist_with_a_real_bridge(tmp_path) -> None:
    settings = Settings.model_validate({**CONFIG, "bridge": {"kind": "mqtt"}})
    app = create_app(settings, store=Store(tmp_path / "state.db"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        for method, url in (
            ("POST", "/api/sim/bridge/shutters"),
            ("DELETE", "/api/sim/bridge/shutters/0x279621"),
            ("POST", "/api/sim/bridge/restart"),
        ):
            response = await http.request(method, url, json={"name": "Bad"})
            assert response.status_code in (404, 405), (method, url)
