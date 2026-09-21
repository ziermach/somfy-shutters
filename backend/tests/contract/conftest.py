from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG


@pytest.fixture
def app_settings() -> Settings:
    return Settings.model_validate(CONFIG)


@pytest.fixture
def bridge(app_settings: Settings) -> SimBridge:
    return SimBridge(addresses=[s.address for s in app_settings.shutter])


@pytest_asyncio.fixture
async def client(tmp_path, app_settings: Settings, bridge: SimBridge) -> AsyncIterator[AsyncClient]:
    """The app, through its real HTTP surface, driven by the simulator."""
    store = Store(tmp_path / "state.db")
    app = create_app(app_settings, store=store, bridge=bridge)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        http.app = app  # type: ignore[attr-defined]
        yield http
