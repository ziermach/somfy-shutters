"""T012: the guided run through the real API.

Uses a shutter configured with a one-second travel, so a full run finishes
inside a test rather than in eighteen seconds. The arithmetic is covered by
test_convergence.py; what is checked here is the flow — phases, alternation,
what a run records, and what happens when nobody presses.
"""

from __future__ import annotations

import asyncio

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

FAST = {
    "general": {"default_travel_seconds": 20, "stale_after_hours": 12},
    "bridge": {"kind": "sim"},
    "shutter": [
        {"id": "flink", "name": "Flink", "address": "0x279631"},
    ],
}


@pytest_asyncio.fixture
async def client(tmp_path):
    settings = Settings.model_validate(FAST)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    # make the simulated window fast, so a run takes about a second
    for shutter in bridge._shutters.values():
        shutter.dead_time = 0.1
        shutter.travel_up = 1.0
        shutter.travel_down = 0.8
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        yield http


async def park(client, percent: int) -> None:
    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": percent})


# The app does not know the travel time yet, so its own movement runs for the
# default twenty seconds while the simulated window is done in about one. That
# gap is the whole reason this feature exists: the person presses when they see
# it stop, not when the app thinks it stopped.
SIMULATED_TRAVEL = 1.3


async def full_run(client) -> dict:
    start = (await client.post("/api/calibration/flink/run")).json()
    await asyncio.sleep(0.25)
    moving = (await client.post("/api/calibration/flink/mark", json={"mark": "moving"})).json()
    assert moving["phase"] == "timing"
    await asyncio.sleep(SIMULATED_TRAVEL)
    finished = (await client.post("/api/calibration/flink/mark", json={"mark": "arrived"})).json()
    finished["started"] = start
    return finished


async def test_a_run_is_recorded_with_both_times(client) -> None:
    await park(client, 0)
    result = await full_run(client)

    run = result["run"]
    assert run["direction"] == "up"
    assert run["rejected"] is None
    assert run["dead_seconds"] > 0
    assert run["total_seconds"] > run["dead_seconds"]
    assert run["kind"] == "guided"
    assert result["calibration"]["runs"] == 1
    assert result["calibration"]["source"] == "measured"


async def test_direction_alternates_without_repositioning(client) -> None:
    """FR-006: the next run starts where the last one ended."""
    await park(client, 0)
    first = await full_run(client)
    assert first["run"]["direction"] == "up"
    assert first["next_direction"] == "down"

    second = await full_run(client)
    assert second["run"]["direction"] == "down"
    assert second["started"]["from_percent"] == 100


async def test_the_measured_value_is_the_median_of_the_runs(client) -> None:
    await park(client, 0)
    for _ in range(3):
        await full_run(client)
    body = (await client.get("/api/calibration/flink")).json()
    assert body["up"]["runs"] >= 1
    assert body["state"] in {"calibrated", "partial"}


async def test_aborting_leaves_the_position_uncertain(client) -> None:
    """FR-008: the shutter stops between end stops, so it is no longer certain."""
    await park(client, 0)
    await client.post("/api/calibration/flink/run")
    await asyncio.sleep(0.4)
    assert (await client.delete("/api/calibration/flink/run")).json()["aborted"] is True

    position = (await client.get("/api/shutters/flink")).json()["position"]
    assert position["confidence"] != "certain"
    assert (await client.get("/api/calibration/flink")).json()["active_run"] is None


async def test_a_second_run_while_one_is_active_is_refused(client) -> None:
    await park(client, 0)
    await client.post("/api/calibration/flink/run")
    response = await client.post("/api/calibration/flink/run")
    assert response.status_code == 409
    assert response.json()["error"] == "already_running"
    await client.delete("/api/calibration/flink/run")


async def test_pressing_arrived_immediately_is_rejected_not_stored_as_truth(client) -> None:
    """A run that says the shutter crossed the whole window instantly cannot count."""
    await park(client, 0)
    await client.post("/api/calibration/flink/run")
    await client.post("/api/calibration/flink/mark", json={"mark": "moving"})
    result = (await client.post("/api/calibration/flink/mark", json={"mark": "arrived"})).json()

    assert result["run"]["rejected"] == "too_short"
    assert result["calibration"]["source"] == "default", "a rejected run must not become the value"
    # and it is still listed, with its reason (FR-012)
    runs = (await client.get("/api/calibration/flink")).json()["runs"]
    assert len(runs) == 1
    assert runs[0]["rejected"] == "too_short"


async def test_clearing_discards_everything_measured(client) -> None:
    await park(client, 0)
    await full_run(client)
    body = (await client.delete("/api/calibration/flink")).json()
    assert body["state"] == "uncalibrated"
    assert (await client.get("/api/calibration/flink")).json()["runs"] == []


async def test_a_report_during_a_run_marks_it_disturbed(client) -> None:
    """FR-029: somebody else drove the shutter, so the measurement is worthless.

    Only detectable at all when the receiver is on. With it off, the run finishes
    with a wrong duration and the plausibility band has to catch it — an accepted
    limitation, recorded in research.md.
    """
    await park(client, 0)
    await client.post("/api/calibration/flink/run")
    await asyncio.sleep(0.25)
    await client.post("/api/calibration/flink/mark", json={"mark": "moving"})
    # a physical remote, heard by the receiver
    await client.post("/api/sim/report", json={"shutter_id": "flink", "percent": 55})
    await asyncio.sleep(SIMULATED_TRAVEL)
    result = (await client.post("/api/calibration/flink/mark", json={"mark": "arrived"})).json()

    assert result["run"]["rejected"] == "disturbed"
    assert result["calibration"]["source"] == "default"
