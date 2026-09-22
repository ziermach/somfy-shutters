"""Feature 005, US1 / quickstart A1: take over the shutters the bridge already knows.

FR-002 (new shutters stay out of the household until confirmed), FR-003 (matched by
address, never duplicated), SC-002 (no duplicates across restarts).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG

EXTRA = {"0x279630": "Bad", "0x279631": "Gästezimmer", "0x279632": "Arbeitszimmer"}


@asynccontextmanager
async def app_for(tmp_path, *, bridge_names: dict[str, str]):
    settings = Settings.model_validate(CONFIG)
    bridge = SimBridge(addresses=list(bridge_names), names=bridge_names)
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        http.app = app  # type: ignore[attr-defined]
        yield http


def everything() -> dict[str, str]:
    names = {s["address"]: s["name"] for s in CONFIG["shutter"]}  # type: ignore[index]
    return names | EXTRA


async def wait_for(predicate, what: str) -> None:
    for _ in range(200):
        if await predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


async def new_count(http) -> int:
    return len((await http.get("/api/roster")).json()["new"])


async def test_new_shutters_stay_out_until_confirmed(tmp_path) -> None:
    async with app_for(tmp_path, bridge_names=everything()) as http:
        await wait_for(lambda: _eq(new_count(http), 3), "three new shutters")
        ids = [s["id"] for s in (await http.get("/api/shutters")).json()["shutters"]]
        assert ids == ["wohnzimmer", "kueche", "schlafzimmer"]

        # "Alle zu" reaches only the household.
        response = await http.post("/api/shutters/command", json={"action": "close"})
        assert [r["id"] for r in response.json()["results"]] == ids

        # A group cannot take an unconfirmed shutter.
        response = await http.post("/api/groups", json={"name": "Oben", "members": ["bad"]})
        assert response.status_code in (404, 422)


async def test_confirmed_shutters_are_drivable_and_unmeasured(tmp_path) -> None:
    async with app_for(tmp_path, bridge_names=everything()) as http:
        await wait_for(lambda: _eq(new_count(http), 3), "three new shutters")
        for address, name in EXTRA.items():
            response = await http.post(f"/api/roster/new/{address}", json={"name": name})
            assert response.status_code == 201
        shutters = {s["id"]: s for s in (await http.get("/api/shutters")).json()["shutters"]}
        assert {"bad", "gaestezimmer", "arbeitszimmer"} <= set(shutters)
        assert shutters["bad"]["calibrated"] is False
        response = await http.post("/api/shutters/bad/command", json={"action": "close"})
        assert response.status_code == 200
        assert response.json()["accepted"] is True


async def test_a_configured_shutter_announced_by_the_bridge_appears_once(tmp_path) -> None:
    names = everything() | {"0x279621": "Living Room"}
    async with app_for(tmp_path, bridge_names=names) as http:
        await wait_for(lambda: _eq(new_count(http), 3), "three new shutters")
        shutters = (await http.get("/api/shutters")).json()["shutters"]
        living = [s for s in shutters if s["id"] == "wohnzimmer"]
        assert len(living) == 1
        assert living[0]["name"] == "Wohnzimmer"
        assert living[0]["travel_up_seconds"] == 18.0
        assert living[0]["origin"] == "config"


async def test_restarts_duplicate_nothing_and_keep_the_persons_name(tmp_path) -> None:
    async with app_for(tmp_path, bridge_names=everything()) as http:
        await wait_for(lambda: _eq(new_count(http), 3), "three new shutters")
        await http.post("/api/roster/new/0x279630", json={"name": "Bad"})
        await http.patch("/api/shutters/bad", json={"name": "Badezimmer"})
        # The bridge restarts and announces everything again, live.
        await http.post("/api/sim/bridge/restart")
        await asyncio.sleep(0.05)
        assert await new_count(http) == 2

    async with app_for(tmp_path, bridge_names=everything()) as http:
        await wait_for(lambda: _eq(new_count(http), 2), "two new shutters")
        shutters = (await http.get("/api/shutters")).json()["shutters"]
        assert [s["id"] for s in shutters].count("bad") == 1
        assert next(s for s in shutters if s["id"] == "bad")["name"] == "Badezimmer"


async def _eq(value, expected) -> bool:
    return (await value) == expected
