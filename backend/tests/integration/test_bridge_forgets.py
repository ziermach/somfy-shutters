"""Feature 005, US4 / quickstart A5: the bridge forgets a shutter.

FR-017, FR-018, SC-005.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from somfy_shutters.automation.models import RuleDraft
from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG


@asynccontextmanager
async def house(tmp_path):
    settings = Settings.model_validate(CONFIG)
    names = {s.address: s.name for s in settings.shutter} | {"0x279630": "Bad"}
    bridge = SimBridge(addresses=list(names), names=names)
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    app.state.roster.window_seconds = 0.1
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        http.app = app  # type: ignore[attr-defined]
        for _ in range(100):
            if (await http.get("/api/roster")).json()["new"]:
                break
            await asyncio.sleep(0.01)
        assert (
            await http.post("/api/roster/new/0x279630", json={"name": "Bad"})
        ).status_code == 201
        yield http


async def forget(http) -> None:
    await http.delete("/api/sim/bridge/shutters/0x279630")
    await http.post("/api/sim/bridge/restart")
    for _ in range(100):
        if (await http.get("/api/shutters/bad")).json()["forgotten"]:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("not marked forgotten")


async def test_forgotten_after_a_restart_without_it(tmp_path) -> None:
    async with house(tmp_path) as http:
        await forget(http)
        body = (await http.get("/api/roster")).json()
        assert [e["id"] for e in body["active"] if e["forgotten"]] == ["bad"]
        response = await http.post("/api/shutters/bad/command", json={"action": "close"})
        assert response.status_code == 409
        assert response.json()["error"] == "forgotten"
        assert response.json()["message"] == "Die Funkbrücke kennt diesen Rolladen nicht mehr."
        # The others still work.
        response = await http.post("/api/shutters/kueche/command", json={"action": "open"})
        assert response.status_code == 200


async def test_all_reports_it_and_moves_the_rest(tmp_path) -> None:
    async with house(tmp_path) as http:
        await forget(http)
        results = (await http.post("/api/shutters/command", json={"action": "stop"})).json()
        by_id = {r["id"]: r for r in results["results"]}
        assert by_id["bad"] == {"id": "bad", "accepted": False, "error": "forgotten"}


async def test_automations_skip_it_with_that_reason(tmp_path) -> None:
    async with house(tmp_path) as http:
        await forget(http)
        engine = http.app.state.automation
        rule = engine.store.create(
            RuleDraft.model_validate(
                {
                    "name": "Bad zu",
                    "days": [True] * 7,
                    "trigger": {"kind": "time", "time": "21:00"},
                    "targets": {"shutters": ["bad"], "groups": []},
                    "action": {"kind": "close"},
                }
            )
        )
        outcomes = await engine._command(rule)
        assert [(o.shutter_id, o.result, o.reason) for o in outcomes] == [
            ("bad", "skipped", "forgotten")
        ]


async def test_settings_are_kept_and_it_comes_back(tmp_path) -> None:
    async with house(tmp_path) as http:
        group = (await http.post("/api/groups", json={"name": "Oben", "members": ["bad"]})).json()
        await forget(http)
        groups = (await http.get("/api/groups")).json()["groups"]
        assert next(g for g in groups if g["id"] == group["id"])["members"] == ["bad"]
        # The person re-adds it in the bridge under the same address and restarts.
        bridge = http.app.state.bridge
        bridge._bridge["0x279630"].enabled = True
        await http.post("/api/sim/bridge/restart")
        for _ in range(100):
            if not (await http.get("/api/shutters/bad")).json()["forgotten"]:
                break
            await asyncio.sleep(0.01)
        assert (await http.get("/api/shutters/bad")).json()["forgotten"] is False
        response = await http.post("/api/shutters/bad/command", json={"action": "open"})
        assert response.status_code == 200


async def test_an_unreachable_bridge_forgets_nothing(tmp_path) -> None:
    async with house(tmp_path) as http:
        await http.post("/api/sim/bridge/offline")
        await asyncio.sleep(0.2)
        assert (await http.get("/api/shutters/bad")).json()["forgotten"] is False
        response = await http.post("/api/shutters/bad/command", json={"action": "close"})
        assert response.status_code == 503
