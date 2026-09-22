"""Quickstart scenarios of feature 004 against the simulator (specs/004-shutter-groups/quickstart.md)."""

from __future__ import annotations

from datetime import datetime

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.models import utcnow
from somfy_shutters.store import Store


def house_of(n: int) -> Settings:
    return Settings.model_validate(
        {
            "general": {"stale_after_hours": 12, "default_travel_seconds": 20},
            "bridge": {"kind": "sim", "invert_level": False},
            "shutter": [
                {"id": f"s{i:02d}", "name": f"Fenster {i}", "address": f"0x2796{i:02d}"}
                for i in range(n)
            ],
        }
    )


@pytest_asyncio.fixture
async def twelve(tmp_path):
    settings = house_of(12)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        yield http


async def test_c6_a_group_of_twelve_is_commanded_within_five_seconds(twelve) -> None:
    """FR-021 / SC-003: from the tap to the last member's command."""
    ids = [f"s{i:02d}" for i in range(12)]
    group = (await twelve.post("/api/groups", json={"name": "Alle zwölf", "members": ids})).json()
    tapped = utcnow()
    response = await twelve.post(f"/api/groups/{group['id']}/command", json={"action": "close"})
    assert response.status_code == 200
    started = [
        datetime.fromisoformat(r["movement"]["started_at"]) for r in response.json()["results"]
    ]
    assert len(started) == 12
    assert (max(started) - tapped).total_seconds() < 5
