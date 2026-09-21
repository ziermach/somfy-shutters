"""T046: FR-021, a command that cannot be delivered says so and does nothing."""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG


@pytest_asyncio.fixture
async def client(tmp_path):
    settings = Settings.model_validate(CONFIG)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        yield http


async def test_command_fails_visibly_and_starts_no_movement(client) -> None:
    await client.post("/api/sim/bridge/offline")

    response = await client.post("/api/shutters/wohnzimmer/command", json={"action": "close"})

    assert response.status_code == 503
    body = response.json()
    assert body["accepted"] is False
    assert body["error"] == "bridge_unreachable"
    assert "Funkbrücke" in body["message"]

    shutter = (await client.get("/api/shutters/wohnzimmer")).json()
    assert shutter["movement"] is None, "nothing may animate that is not happening"


async def test_nothing_is_queued_for_later(client) -> None:
    """A shutter closing twenty minutes late is worse than one that never closed."""
    await client.post("/api/sim/bridge/offline")
    await client.post("/api/shutters/wohnzimmer/command", json={"action": "close"})

    await client.post("/api/sim/bridge/online")

    shutter = (await client.get("/api/shutters/wohnzimmer")).json()
    assert shutter["movement"] is None


async def test_all_shutters_failing_is_503(client) -> None:
    await client.post("/api/sim/bridge/offline")
    response = await client.post("/api/shutters/command", json={"action": "open"})
    assert response.status_code == 503
    assert all(r["accepted"] is False for r in response.json()["results"])


async def test_the_bridge_state_is_visible(client) -> None:
    await client.post("/api/sim/bridge/offline")
    assert (await client.get("/api/shutters")).json()["bridge"]["connected"] is False
    await client.post("/api/sim/bridge/online")
    assert (await client.get("/api/shutters")).json()["bridge"]["connected"] is True
