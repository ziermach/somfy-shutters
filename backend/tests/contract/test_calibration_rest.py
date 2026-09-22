"""T011: the calibration surface matches contracts/rest.md."""

from __future__ import annotations

DIRECTION_KEYS = {"travel_seconds", "dead_seconds", "runs", "curve_a", "source", "updated_at"}


async def park(client, shutter_id: str, percent: int) -> None:
    """Put a shutter at a known position instantly.

    Every shutter starts unknown on a fresh database — which is correct, and
    means a calibration run cannot start until something establishes where it
    is. A simulator report does that without waiting for a real travel.
    """
    await client.post("/api/sim/report", json={"shutter_id": shutter_id, "percent": percent})


async def test_list_shape(client) -> None:
    body = (await client.get("/api/calibration")).json()
    assert set(body) == {"shutters"}
    for shutter in body["shutters"]:
        assert set(shutter) == {"id", "name", "state", "up", "down"}
        assert shutter["state"] in {"calibrated", "partial", "uncalibrated", "manual"}
        assert set(shutter["up"]) == DIRECTION_KEYS
        assert set(shutter["down"]) == DIRECTION_KEYS


async def test_source_says_which_layer_won(client) -> None:
    body = (await client.get("/api/calibration")).json()
    by_id = {s["id"]: s for s in body["shutters"]}
    # the fixture gives wohnzimmer hand-written times in both directions
    assert by_id["wohnzimmer"]["up"]["source"] == "manual"
    # schlafzimmer has none at all
    assert by_id["schlafzimmer"]["up"]["source"] == "default"
    assert by_id["schlafzimmer"]["state"] == "uncalibrated"


async def test_starting_away_from_an_end_stop_is_409_with_a_suggestion(client) -> None:
    await park(client, "schlafzimmer", 40)
    response = await client.post("/api/calibration/schlafzimmer/run")
    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "not_at_end_stop"
    assert body["suggested_target"] in (0, 100)


async def test_unknown_shutter_is_404(client) -> None:
    assert (await client.post("/api/calibration/keller/run")).status_code == 404
    assert (await client.get("/api/calibration/keller")).status_code == 404


async def test_mark_without_a_run_is_409(client) -> None:
    response = await client.post("/api/calibration/kueche/mark", json={"mark": "moving"})
    assert response.status_code == 409
    assert response.json()["error"] == "no_run"


async def test_detail_carries_runs_and_the_active_run(client) -> None:
    body = (await client.get("/api/calibration/kueche")).json()
    assert body["runs"] == []
    assert body["active_run"] is None


async def test_a_command_during_a_measurement_is_refused_with_a_reason(client) -> None:
    """FR-028: refused loudly, not swallowed."""
    await park(client, "kueche", 0)
    assert (await client.post("/api/calibration/kueche/run")).status_code == 200
    response = await client.post("/api/shutters/kueche/command", json={"action": "open"})
    assert response.status_code == 409
    assert response.json()["error"] == "measurement_in_progress"
    await client.delete("/api/calibration/kueche/run")


async def test_home_is_not_a_measurement(client) -> None:
    await park(client, "schlafzimmer", 40)
    body = (await client.post("/api/calibration/schlafzimmer/home")).json()
    assert body["measured"] is False
    assert body["target_percent"] in (0, 100)
    assert (await client.get("/api/calibration/schlafzimmer")).json()["runs"] == []


async def test_an_unknown_position_cannot_start_a_run(client) -> None:
    """A fresh start knows nothing, and a measurement must not begin on a guess."""
    response = await client.post("/api/calibration/kueche/run")
    assert response.status_code == 409
    assert response.json()["error"] == "not_at_end_stop"
    assert response.json()["suggested_target"] == 100


async def test_all_shutters_command_leaves_a_measurement_alone(client) -> None:
    """FR-028, by the route that got past the guard.

    The check sat on the single-shutter endpoint only, so "Alle zu" drove
    straight through a running measurement — found by somebody pressing it while
    a calibration was going.
    """
    await park(client, "kueche", 0)
    assert (await client.post("/api/calibration/kueche/run")).status_code == 200

    response = await client.post("/api/shutters/command", json={"action": "close"})
    results = {r["id"]: r for r in response.json()["results"]}

    assert results["kueche"]["accepted"] is False
    assert results["kueche"]["error"] == "measurement_in_progress"
    assert results["wohnzimmer"]["accepted"] is True, "the others still move"
    assert response.status_code == 207

    detail = (await client.get("/api/calibration/kueche")).json()
    assert detail["active_run"] is not None, "the run survived the command"
    await client.delete("/api/calibration/kueche/run")
