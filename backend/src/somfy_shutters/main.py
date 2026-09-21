"""The application: wiring, lifespan, static files.

One process in production — the built frontend is served from here, so there is
no second origin and nothing to configure.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import rest, ws
from .bridge.base import ShutterBridge
from .bridge.mqtt import MqttBridge
from .bridge.sim import SimBridge
from .config import Settings, load_settings
from .events import EventBus
from .store import Store
from .tracker import Tracker

log = logging.getLogger(__name__)

TICK_SECONDS = 0.2
"""How often settled movements are noticed. The animation runs client-side, so
this only decides when the model catches up — not how smooth anything looks."""

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO_ROOT / "config" / "shutters.toml"
DEFAULT_DB = REPO_ROOT / "config" / "state.db"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


def build_bridge(settings: Settings) -> ShutterBridge:
    if settings.bridge.kind == "sim":
        return SimBridge(addresses=[s.address for s in settings.shutter])
    return MqttBridge(settings.bridge)


def create_app(
    settings: Settings | None = None,
    *,
    store: Store | None = None,
    bridge: ShutterBridge | None = None,
) -> FastAPI:
    settings = settings or load_settings(os.environ.get("SHUTTERS_CONFIG", DEFAULT_CONFIG))
    bridge = bridge or build_bridge(settings)
    store = store or Store(os.environ.get("SHUTTERS_DB", DEFAULT_DB))
    bus = EventBus()
    hub = ws.Hub()

    async def emit(event: dict[str, Any]) -> None:
        await bus.publish(event)

    tracker = Tracker(settings, store, emit=emit)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async def to_clients(event: dict[str, Any]) -> None:
            frame = ws.frame_for_event(event, tracker)
            if frame is not None:
                await hub.broadcast(frame)

        bus.subscribe(to_clients)

        # A reference is kept: a task only referenced by the event loop can be
        # garbage-collected mid-flight.
        pending: set[asyncio.Task[None]] = set()

        def bridge_changed(connected: bool) -> None:
            task = asyncio.create_task(
                bus.publish({"type": "bridge", "connected": connected, "kind": bridge.kind})
            )
            pending.add(task)
            task.add_done_callback(pending.discard)

        bridge.on_connection_change(bridge_changed)
        await bridge.start()

        async def pump_reports() -> None:
            async for report in bridge.reports():
                await tracker.handle_report(report.address, report.percent)

        async def pump_ticks() -> None:
            while True:
                await tracker.tick()
                await asyncio.sleep(TICK_SECONDS)

        tasks = [asyncio.create_task(pump_reports()), asyncio.create_task(pump_ticks())]
        log.info("ready: %d shutters, bridge=%s", len(settings.shutters), bridge.kind)
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await bridge.stop()
            store.close()

    app = FastAPI(title="somfy-shutters", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.tracker = tracker
    app.state.bridge = bridge
    app.state.store = store
    app.state.bus = bus
    app.state.hub = hub

    app.include_router(rest.router)
    app.include_router(ws.router)
    if settings.bridge.kind == "sim":
        app.include_router(rest.sim_router)

    @app.exception_handler(404)
    async def not_found(request: Any, exc: Any) -> JSONResponse:
        detail = getattr(exc, "detail", None)
        if isinstance(detail, dict):
            return JSONResponse(detail, status_code=404)
        return JSONResponse(
            {"error": "not_found", "message": "Nicht gefunden.", "detail": None}, status_code=404
        )

    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    else:
        log.warning("no built frontend at %s — run `npm run build`", FRONTEND_DIST)

    return app


configure_logging()

_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    """Build the app only when something actually asks for it.

    `uvicorn somfy_shutters.main:app` gets a real application; importing the
    module in a test does not, so tests can build their own with a temporary
    config and an in-memory store instead of tripping over the real one.
    """
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
