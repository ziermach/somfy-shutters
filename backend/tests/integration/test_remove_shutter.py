"""Feature 005, US3 / quickstart A4: removing a shutter.

FR-012 to FR-016, SC-004: gone from every screen, group and rule; nothing sent to the
bridge; kept aside while the bridge still announces it; restorable.
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


class RecordingBridge(SimBridge):
    """The simulator, noting every command handed to it."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.sent: list[tuple[str, str]] = []

    async def send_level(self, address: str, percent: int) -> None:
        self.sent.append((address, f"level {percent}"))
        await super().send_level(address, percent)

    async def send_stop(self, address: str) -> None:
        self.sent.append((address, "stop"))
        await super().send_stop(address)


@asynccontextmanager
async def house(tmp_path):
    settings = Settings.model_validate(CONFIG)
    names = {s.address: s.name for s in settings.shutter} | {"0x279630": "Bad"}
    bridge = RecordingBridge(addresses=list(names), names=names)
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        http.app = app  # type: ignore[attr-defined]
        http.bridge = bridge  # type: ignore[attr-defined]
        for _ in range(100):
            if (await http.get("/api/roster")).json()["new"]:
                break
            await asyncio.sleep(0.01)
        assert (
            await http.post("/api/roster/new/0x279630", json={"name": "Bad"})
        ).status_code == 201
        yield http


def rule(name: str, shutters: list[str], groups: list[str] | None = None) -> dict:
    return {
        "name": name,
        "days": [True] * 7,
        "trigger": {"kind": "time", "time": "21:00"},
        "targets": {"shutters": shutters, "groups": groups or []},
        "action": {"kind": "close"},
    }


async def test_the_whole_cascade(tmp_path) -> None:
    async with house(tmp_path) as http:
        app = http.app
        group = (await http.post("/api/groups", json={"name": "Oben", "members": ["bad"]})).json()
        mixed = (
            await http.post("/api/groups", json={"name": "Alle", "members": ["bad", "kueche"]})
        ).json()
        alone = (await http.post("/api/automations", json=rule("Bad zu", ["bad"]))).json()
        shared = (
            await http.post("/api/automations", json=rule("Abends zu", ["bad", "kueche"]))
        ).json()
        cleared: list[str] = []
        original = app.state.calibration.clear
        app.state.calibration.clear = lambda sid: (cleared.append(sid), original(sid))
        await http.post("/api/shutters/bad/command", json={"action": "close"})
        sent_before = list(http.bridge.sent)

        preview = (await http.get("/api/shutters/bad/removal")).json()
        assert {g["name"] for g in preview["groups"]} == {"Oben", "Alle"}
        assert {r["name"]: r["left_without_target"] for r in preview["rules"]} == {
            "Bad zu": True,
            "Abends zu": False,
        }

        # Removed while travelling: allowed, and nothing — not even a stop — is sent.
        response = await http.delete("/api/shutters/bad")
        assert response.json() == {"removed": "bad", "set_aside": True}
        assert http.bridge.sent == sent_before

        assert "bad" not in app.state.settings.shutters
        assert "bad" not in [s["id"] for s in (await http.get("/api/shutters")).json()["shutters"]]
        assert app.state.tracker.movement("bad") is None
        assert "bad" not in app.state.store.load_all()
        assert cleared == ["bad"]

        groups = {g["id"]: g for g in (await http.get("/api/groups")).json()["groups"]}
        assert groups[group["id"]]["members"] == [], "an emptied group stays"
        assert groups[mixed["id"]]["members"] == ["kueche"]

        rules = {r["id"]: r for r in (await http.get("/api/automations")).json()["rules"]}
        assert rules[alone["id"]]["targets"] == {"shutters": [], "groups": []}
        assert rules[alone["id"]]["next"]["reason"] == "no_targets"
        assert rules[shared["id"]]["targets"]["shutters"] == ["kueche"]

        row = app.state.roster.rows.by_address("0x279630")
        assert row.state == "set_aside"


async def test_set_aside_does_not_return_as_new_after_a_bridge_restart(tmp_path) -> None:
    async with house(tmp_path) as http:
        await http.delete("/api/shutters/bad")
        await http.post("/api/sim/bridge/restart")
        await asyncio.sleep(0.05)
        body = (await http.get("/api/roster")).json()
        assert body["new"] == []
        assert body["set_aside"] == [{"address": "0x279630", "name": "Bad"}]


async def test_restore_then_confirm_starts_fresh(tmp_path) -> None:
    async with house(tmp_path) as http:
        await http.post("/api/sim/report", json={"shutter_id": "bad", "percent": 100})
        await http.delete("/api/shutters/bad")
        await http.post("/api/roster/set-aside/0x279630/restore")
        response = await http.post("/api/roster/new/0x279630", json={"name": "Badezimmer"})
        assert response.status_code == 201
        shutter = response.json()
        assert shutter["id"] == "badezimmer"
        assert shutter["calibrated"] is False
        assert shutter["position"]["confidence"] == "unknown"


async def test_removed_without_announcement_leaves_no_row(tmp_path) -> None:
    async with house(tmp_path) as http:
        roster = http.app.state.roster
        roster.announced.pop("0x279630")
        response = await http.delete("/api/shutters/bad")
        assert response.json()["set_aside"] is False
        assert roster.rows.by_address("0x279630") is None
