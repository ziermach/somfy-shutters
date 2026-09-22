"""T014 (FR-027): switching the door on keeps everything the house already knew."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from somfy_shutters.auth.models import ALL_ABILITIES
from somfy_shutters.auth.store import AuthStore
from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG

BERLIN = ZoneInfo("Europe/Berlin")
KEPT = (
    "shutter_state",
    "automation_rule",
    "automation_firing",
    "shutter_group",
    "shutter_group_member",
    "app_setting",
)


def counts(db) -> dict[str, int]:
    conn = sqlite3.connect(db)
    out = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in KEPT}
    conn.close()
    return out


def app_on(db, mode: str | None):
    auth = {"mode": mode} if mode else {}
    settings = Settings.model_validate({**CONFIG, "auth": auth})
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    return create_app(settings, store=Store(db), bridge=bridge)


def test_an_installation_from_before_keeps_everything(tmp_path) -> None:
    db = tmp_path / "state.db"
    with TestClient(app_on(db, None)) as before:  # as it ran before feature 008: open
        before.post("/api/shutters/wohnzimmer/command", json={"action": "close"})
        before.post("/api/groups", json={"name": "Unten", "members": ["wohnzimmer", "kueche"]})
        before.put("/api/location", json={"latitude": 52.52, "longitude": 13.40})
        rule = before.post(
            "/api/automations",
            json={
                "name": "Abends",
                "days": [True] * 7,
                "trigger": {"kind": "time", "time": "20:00"},
                "targets": "all",
                "action": {"kind": "close"},
            },
        ).json()
        engine = before.app.state.automation
        before.portal.call(engine.run_due, datetime(2026, 9, 22, 20, 0, tzinfo=BERLIN))
    had = counts(db)
    assert all(had.values()), had

    with TestClient(app_on(db, "required")) as after:
        assert after.get("/api/automations").status_code == 401
        assert counts(db) == had
        _, code = AuthStore(db).mint(ALL_ABILITIES, None, 15)  # somfy-shutters auth recover
        assert (
            after.post("/api/auth/pair", json={"code": code, "name": "Laptop"}).status_code == 201
        )
        rules = after.get("/api/automations").json()["rules"]
        assert [r["id"] for r in rules] == [rule["id"]]
        assert rules[0]["last"]["status"] == "fired"
        assert after.get("/api/groups").json()["groups"][0]["name"] == "Unten"
        assert after.get("/api/location").json()["latitude"] == 52.52
    assert counts(db) == had
