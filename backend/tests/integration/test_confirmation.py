"""T025 and T026: the one tap that keeps travel times true.

The travel itself measures nothing — the arrival we computed came from the very
number we want to find out. Only the tap is an observation, and these tests hold
the code to that: no prompt, no measurement.
"""

from __future__ import annotations

import asyncio

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

CONFIG = {
    "general": {"default_travel_seconds": 2, "stale_after_hours": 12},
    "bridge": {"kind": "sim"},
    "shutter": [{"id": "flink", "name": "Flink", "address": "0x279631"}],
}


@pytest_asyncio.fixture
async def client(tmp_path):
    settings = Settings.model_validate(CONFIG)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    for shutter in bridge._shutters.values():
        shutter.dead_time = 0.1
        shutter.travel_up = 1.0
        shutter.travel_down = 0.8
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        http.app = app  # type: ignore[attr-defined]
        yield http


async def park(client, percent: int) -> None:
    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": percent})


async def travel_and_wait(client, action: str) -> None:
    await client.post("/api/shutters/flink/command", json={"action": action})
    # the app's own movement lasts default_travel_seconds; wait it out so the
    # settle fires and the question is offered
    await asyncio.sleep(2.6)


def pending(client) -> dict:
    return client.app.state.pending_confirmations


async def test_an_end_to_end_travel_offers_one_question(client) -> None:
    await park(client, 0)
    await travel_and_wait(client, "open")
    assert "flink" in pending(client)


async def test_a_partial_travel_offers_nothing(client) -> None:
    """FR-019: nothing may be derived from a travel that did not run end to end."""
    await park(client, 0)
    await client.post(
        "/api/shutters/flink/command", json={"action": "position", "target_percent": 60}
    )
    await asyncio.sleep(2.2)
    assert "flink" not in pending(client)


async def test_confirming_records_a_measurement(client) -> None:
    await park(client, 0)
    await travel_and_wait(client, "open")

    body = (await client.post("/api/calibration/flink/confirm")).json()
    assert body["run"]["kind"] == "confirmed"
    assert body["run"]["rejected"] is None
    assert body["calibration"]["runs"] == 1
    assert body["calibration"]["source"] == "measured"


async def test_the_measured_time_is_when_the_tap_happened(client) -> None:
    """Not the app's computed arrival, which is the number being measured."""
    await park(client, 0)
    await client.post("/api/shutters/flink/command", json={"action": "open"})
    await asyncio.sleep(2.6)
    await asyncio.sleep(0.7)  # the user notices the question a little later

    body = (await client.post("/api/calibration/flink/confirm")).json()
    assert body["run"]["total_seconds"] > 3.0, "the tap's moment is what counts"


async def test_ignoring_the_question_records_nothing(client) -> None:
    """FR-018a: silence is not an answer."""
    await park(client, 0)
    await travel_and_wait(client, "open")

    await client.delete("/api/calibration/flink/confirm")
    assert "flink" not in pending(client)
    assert (await client.get("/api/calibration/flink")).json()["runs"] == []


async def test_confirming_twice_is_refused(client) -> None:
    await park(client, 0)
    await travel_and_wait(client, "open")
    assert (await client.post("/api/calibration/flink/confirm")).status_code == 200

    second = await client.post("/api/calibration/flink/confirm")
    assert second.status_code == 409
    assert second.json()["error"] == "nothing_to_confirm"


async def test_the_question_is_asked_at_most_once_a_day(client) -> None:
    """FR-018a: a question after every travel would be nagging, not helping."""
    await park(client, 0)
    await travel_and_wait(client, "open")
    await client.delete("/api/calibration/flink/confirm")

    await travel_and_wait(client, "close")
    assert "flink" not in pending(client), "asked again on the same day"


async def test_a_confirmed_run_is_distinguishable_in_the_history(client) -> None:
    """FR-020: a tap and a guided run are not the same quality of evidence."""
    await park(client, 0)
    await travel_and_wait(client, "open")
    await client.post("/api/calibration/flink/confirm")

    runs = (await client.get("/api/calibration/flink")).json()["runs"]
    assert [r["kind"] for r in runs] == ["confirmed"]
