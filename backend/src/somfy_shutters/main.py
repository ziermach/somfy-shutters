"""The application: wiring, lifespan, static files.

One process in production — the built frontend is served from here, so there is
no second origin and nothing to configure.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import automation_routes, calibration_routes, group_routes, rest, ws
from .auth.audit import AuditLog
from .auth.store import AuthStore
from .automation.clock import ClockGuard
from .automation.engine import LOCATION_KEY, AutomationEngine
from .automation.store import AutomationStore
from .bridge.base import ShutterBridge
from .bridge.mqtt import MqttBridge
from .bridge.sim import SimBridge
from .calibration import (
    PendingConfirmation,
    RejectionReason,
    RunRegistry,
    may_ask_for_confirmation,
)
from .calibration_store import CalibrationService, CalibrationStore
from .config import Settings, load_settings
from .events import EventBus
from .groups import GroupStore
from .models import utcnow
from .store import Store
from .tracker import Tracker

log = logging.getLogger(__name__)

TICK_SECONDS = 0.2
AUTOMATION_CHECK_SECONDS = 30
"""Clock check and a backstop run_due; the timer itself is APScheduler's."""
"""How often settled movements are noticed. The animation runs client-side, so
this only decides when the model catches up — not how smooth anything looks."""

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO_ROOT / "config" / "shutters.toml"
DEFAULT_DB = REPO_ROOT / "config" / "state.db"
DEFAULT_CALIBRATION = REPO_ROOT / "config" / "calibration.toml"
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
    calibration_store: CalibrationStore | None = None,
) -> FastAPI:
    settings = settings or load_settings(os.environ.get("SHUTTERS_CONFIG", DEFAULT_CONFIG))
    bridge = bridge or build_bridge(settings)
    store = store or Store(os.environ.get("SHUTTERS_DB", DEFAULT_DB))
    bus = EventBus()
    hub = ws.Hub()

    async def emit(event: dict[str, Any]) -> None:
        await bus.publish(event)

    if calibration_store is None:
        # Follow the store we were given. Defaulting to the configured path here
        # would have tests writing into the real database beside the live one.
        db_path = store.path
        toml_path = (
            Path(os.environ["SHUTTERS_CALIBRATION"])
            if "SHUTTERS_CALIBRATION" in os.environ
            else db_path.parent / "calibration.toml"
        )
        calibration_store = CalibrationStore(db_path, toml_path)
    calibration = CalibrationService(settings, calibration_store)

    automation_store = AutomationStore(store.path)
    group_store = GroupStore(store.path)
    auth_store = AuthStore(store.path)
    audit = AuditLog(store.path)
    # The configuration only changes across a restart, so this is the one moment a
    # shutter can have left it (feature 004, FR-009).
    if group_store.prune(list(settings.shutters)):
        log.info("groups: dropped members no longer configured")
    if automation_store.setting(LOCATION_KEY) is None and settings.location is not None:
        # Seeds once. From then on the app is where the location is changed.
        automation_store.set_setting(LOCATION_KEY, settings.location.model_dump())
    guard = ClockGuard()
    # `state` is set to app.state below, once it exists: the engine commands
    # shutters through the same function a button press uses (commands.apply).
    engine = AutomationEngine(
        automation_store, state=None, publish=bus.publish, guard=guard, groups=group_store
    )
    runs = RunRegistry()

    tracker = Tracker(settings, store, emit=emit, calibration=calibration)
    if isinstance(bridge, SimBridge):
        # A real house does not move while the server restarts. A simulated one
        # that snapped back to its defaults instead made every restart look like
        # somebody had driven the shutters, and the app correct itself in steps.
        for shutter in settings.shutter:
            position = tracker.position(shutter.id)
            counter = tracker.bridge_level(shutter.id)
            if position.percent is not None and counter is not None:
                bridge.place(shutter.address, position.percent, believed=counter)

    pending: dict[str, PendingConfirmation] = {}

    async def note_confirmable(event: dict[str, Any]) -> None:
        """Decide whether a finished travel is worth one question.

        No measurement comes from the travel itself — the arrival we computed is
        the travel time we would be measuring. Only a person saying "yes, it is
        up" is an observation (research.md §1).
        """
        if event.get("type") != "position":
            return
        movement = event.get("settled_movement")
        if movement is None:
            return
        shutter_id = event["shutter_id"]
        end_to_end = {movement.from_percent, movement.target_percent} == {0, 100}
        if not may_ask_for_confirmation(
            was_end_to_end=end_to_end,
            was_interrupted=False,
            initiated_by_us=movement.origin.value == "local",
            last_asked=calibration_store.last_prompt(shutter_id),
        ):
            return
        if runs.is_measuring(shutter_id):
            return  # a guided run is already measuring this one properly
        now = utcnow()
        calibration_store.note_prompt(shutter_id, now)
        pending[shutter_id] = PendingConfirmation(
            shutter_id=shutter_id,
            direction=movement.direction,
            started_monotonic=movement.started_monotonic,
            asked_at=now,
        )
        await bus.publish(
            {
                "type": "confirmable",
                "shutter_id": shutter_id,
                "direction": movement.direction.value,
                "name": settings.shutters[shutter_id].name,
            }
        )

    async def on_report(address: str, percent: int) -> None:
        """Every report goes through here, from the bridge or from the simulator.

        A report for a shutter under measurement is usually the bridge narrating
        the travel we ourselves started. Only motion against the commanded
        direction means somebody else is driving, and only that invalidates the
        run (FR-029).
        """
        shutter = settings.by_address(address)
        if shutter is not None and runs.is_measuring(shutter.id):
            runs.note_report(shutter.id, percent)
        await tracker.handle_report(address, percent)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async def to_clients(event: dict[str, Any]) -> None:
            frame = ws.frame_for_event(event, tracker)
            if frame is not None:
                await hub.broadcast(frame)

        bus.subscribe(to_clients)
        bus.subscribe(note_confirmable)

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
                await on_report(report.address, report.percent)

        async def pump_ticks() -> None:
            while True:
                await tracker.tick()
                for stale in runs.sweep(time.monotonic()):
                    # FR-009: nobody pressed "arrived". Record why, and let go of
                    # the shutter — a measurement must never leave a window stuck.
                    run = stale.finish(
                        time.monotonic(),
                        calibration.established_total(stale.shutter_id, stale.direction),
                    )
                    calibration.record(
                        run.model_copy(update={"rejected": RejectionReason.ABANDONED})
                    )
                    log.info(
                        "calibration run on %s abandoned, nobody confirmed arrival",
                        stale.shutter_id,
                    )
                    await bus.publish(
                        {
                            "type": "measuring",
                            "shutter_id": stale.shutter_id,
                            "active": False,
                            "direction": None,
                        }
                    )
                await asyncio.sleep(TICK_SECONDS)

        async def pump_automations() -> None:
            last_beat = 0.0
            last_day = None
            while True:
                try:
                    await engine.check_clock()
                    # A backstop for the timer: idempotent, since every firing is
                    # recorded before it is carried out.
                    await engine.run_due()
                    if time.monotonic() - last_beat >= 60:
                        engine.beat()
                        last_beat = time.monotonic()
                    today = utcnow().astimezone(settings.general.tz).date()
                    if today != last_day:
                        # Sun times move every day; firings older than 90 days go.
                        engine.reschedule()
                        engine.purge()
                        last_day = today
                except Exception:
                    log.exception("automation loop")
                await asyncio.sleep(AUTOMATION_CHECK_SECONDS)

        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        # Started here, on uvicorn's loop; started at import it would bind to another.
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.start()
        engine.scheduler = scheduler
        engine.verdict = guard.check(utcnow(), engine.heartbeat())
        if engine.verdict.reliable:
            await engine.catch_up()
        engine.reschedule()

        tasks = [
            asyncio.create_task(pump_reports()),
            asyncio.create_task(pump_ticks()),
            asyncio.create_task(pump_automations()),
        ]
        log.info("ready: %d shutters, bridge=%s", len(settings.shutters), bridge.kind)
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            scheduler.shutdown(wait=False)
            await bridge.stop()
            store.close()
            calibration_store.close()
            automation_store.close()
            group_store.close()
            auth_store.close()
            audit.close()

    app = FastAPI(title="somfy-shutters", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.tracker = tracker
    app.state.bridge = bridge
    app.state.store = store
    app.state.bus = bus
    app.state.hub = hub
    app.state.calibration = calibration
    app.state.calibration_store = calibration_store
    app.state.runs = runs
    app.state.on_report = on_report
    app.state.pending_confirmations = pending
    # shutter id -> the direction its check drive went. One answer per drive.
    app.state.pending_checks = {}
    app.state.automation = engine
    app.state.groups = group_store
    app.state.auth = auth_store
    app.state.audit = audit
    app.state.clock_guard = guard
    engine.state = app.state

    app.include_router(rest.router)
    app.include_router(calibration_routes.router)
    app.include_router(automation_routes.router)
    app.include_router(group_routes.router)
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
