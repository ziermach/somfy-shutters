"""T037 / quickstart C4.2: a value somebody typed wins, and survives a restart.

The app writes measurements to its own file and never to shutters.toml. So a
number a person put there has to beat anything measured afterwards, the
interface has to be able to say why, and the measurement must still be there if
they remove the override again.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.models import Direction, MeasurementRun, RunKind, utcnow
from somfy_shutters.store import Store

BASE = {
    "general": {"default_travel_seconds": 20, "stale_after_hours": 12},
    "bridge": {"kind": "sim"},
    "shutter": [{"id": "flink", "name": "Flink", "address": "0x279631"}],
}

WITH_OVERRIDE = {
    **BASE,
    "shutter": [
        {"id": "flink", "name": "Flink", "address": "0x279631", "travel_up_seconds": 25.0}
    ],
}


def build(tmp_path, config: dict):
    settings = Settings.model_validate(config)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    return create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)


async def open_client(app) -> AsyncIterator[AsyncClient]:
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        http.app = app  # type: ignore[attr-defined]
        yield http


@pytest_asyncio.fixture
async def measured(tmp_path):
    """A shutter measured at 12 s, with no hand-written value yet."""
    app = build(tmp_path, BASE)
    async for client in open_client(app):
        for _ in range(3):
            app.state.calibration.record(
                MeasurementRun(
                    shutter_id="flink",
                    direction=Direction.UP,
                    dead_seconds=0.6,
                    total_seconds=12.0,
                    kind=RunKind.GUIDED,
                    recorded_at=utcnow(),
                )
            )
        yield client, tmp_path


async def test_the_measurement_is_used_before_anyone_overrides_it(measured) -> None:
    client, _ = measured
    body = (await client.get("/api/calibration/flink")).json()
    assert body["up"]["travel_seconds"] == 12.0
    assert body["up"]["source"] == "measured"
    assert body["state"] in {"calibrated", "partial"}


async def test_a_hand_written_value_wins_after_a_restart(measured) -> None:
    """Somebody edits shutters.toml and restarts the service."""
    _, tmp_path = measured
    app = build(tmp_path, WITH_OVERRIDE)
    async for client in open_client(app):
        body = (await client.get("/api/calibration/flink")).json()

        assert body["up"]["travel_seconds"] == 25.0
        assert body["up"]["source"] == "manual"
        assert body["state"] == "manual", "the interface needs to be able to say so"
        return
    raise AssertionError("client never yielded")


async def test_the_measurement_is_kept_not_discarded(measured) -> None:
    """Overriding hides a measurement. Deleting it would be a different thing."""
    _, tmp_path = measured
    app = build(tmp_path, WITH_OVERRIDE)
    async for client in open_client(app):
        body = (await client.get("/api/calibration/flink")).json()
        assert body["up"]["runs"] == 3
        assert len([r for r in body["runs"] if r["direction"] == "up"]) == 3
        return
    raise AssertionError("client never yielded")


async def test_removing_the_override_brings_the_measurement_back(measured) -> None:
    _, tmp_path = measured
    async for _ in open_client(build(tmp_path, WITH_OVERRIDE)):
        break
    app = build(tmp_path, BASE)
    async for client in open_client(app):
        body = (await client.get("/api/calibration/flink")).json()
        assert body["up"]["travel_seconds"] == 12.0
        assert body["up"]["source"] == "measured"
        return
    raise AssertionError("client never yielded")


async def test_the_animation_uses_the_hand_written_value(measured) -> None:
    """Not just the display: the shutter actually travels on the override."""
    _, tmp_path = measured
    app = build(tmp_path, WITH_OVERRIDE)
    async for client in open_client(app):
        await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": 0})
        body = (await client.post("/api/shutters/flink/command", json={"action": "open"})).json()

        started = body["movement"]["started_at"]
        arrival = body["movement"]["expected_arrival"]
        from datetime import datetime

        duration = (datetime.fromisoformat(arrival) - datetime.fromisoformat(started)).total_seconds()
        assert abs(duration - 25.0) < 0.1, "the measurement must not be what it travels on"
        return
    raise AssertionError("client never yielded")


async def test_new_measurements_still_accumulate_under_an_override(measured) -> None:
    """They are recorded and ignored, so removing the override later is useful."""
    _, tmp_path = measured
    app = build(tmp_path, WITH_OVERRIDE)
    async for client in open_client(app):
        app.state.calibration.record(
            MeasurementRun(
                shutter_id="flink",
                direction=Direction.UP,
                dead_seconds=0.6,
                total_seconds=12.5,
                kind=RunKind.CONFIRMED,
                recorded_at=utcnow(),
            )
        )
        body = (await client.get("/api/calibration/flink")).json()
        assert body["up"]["travel_seconds"] == 25.0, "still overridden"
        assert body["up"]["runs"] == 4, "and still counting"
        return
    raise AssertionError("client never yielded")
