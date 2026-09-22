"""The app with the door shut: the simulator, but `[auth] mode = "required"` (feature 008)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from somfy_shutters.auth.models import ALL_ABILITIES, Ability
from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG

ORIGIN = "http://test"


def required_settings(**auth) -> Settings:
    return Settings.model_validate({**CONFIG, "auth": {"mode": "required", **auth}})


@pytest_asyncio.fixture
async def locked(tmp_path) -> AsyncIterator[AsyncClient]:
    settings = required_settings()
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as http,
        app.router.lifespan_context(app),
    ):
        http.app = app  # type: ignore[attr-defined]
        yield http


def issue(client: AsyncClient, name: str = "Owner", abilities=ALL_ABILITIES, **kw) -> tuple:
    """A credential straight from the store, and the header that presents it."""
    credential, token = client.app.state.auth.issue(name, frozenset(abilities), **kw)
    return credential, {"Authorization": f"Bearer {token}"}, token


def only(*abilities: Ability) -> frozenset[Ability]:
    return frozenset(abilities)
