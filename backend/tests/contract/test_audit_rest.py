"""T033: explaining a movement afterwards (user story 5, FR-014 to FR-018)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from somfy_shutters.auth.models import Ability

from .locked import issue, locked, only  # noqa: F401 — fixture

BERLIN = ZoneInfo("Europe/Berlin")


async def record(client, headers, **query) -> dict:
    response = await client.get("/api/audit", params=query, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def close(client, headers, shutter="wohnzimmer") -> None:
    response = await client.post(
        f"/api/shutters/{shutter}/command", json={"action": "close"}, headers=headers
    )
    assert response.status_code == 200


async def test_who_asked_newest_first(locked) -> None:  # noqa: F811
    _, owner, _ = issue(locked, "Laptop")
    _, anna, _ = issue(locked, "Anna", abilities=only(Ability.COMMAND))
    await close(locked, owner)
    await close(locked, anna)
    got = await record(locked, owner, shutter="wohnzimmer")
    commands = [e for e in got["entries"] if e["action"] == "command"]
    assert [e["actor"]["name"] for e in commands] == ["Anna", "Laptop"]
    assert all(e["outcome"] == "accepted" and e["detail"] == {"action": "close"} for e in commands)
    assert commands[0]["id"] > commands[1]["id"]


async def test_filter_by_device_and_paging(locked) -> None:  # noqa: F811
    laptop, owner, _ = issue(locked, "Laptop")
    for shutter in ("wohnzimmer", "kueche", "schlafzimmer"):
        await close(locked, owner, shutter)
    mine = await record(locked, owner, actor=laptop.id)
    assert {e["actor"]["id"] for e in mine["entries"]} == {laptop.id}
    first = await record(locked, owner, limit=2)
    assert len(first["entries"]) == 2 and first["next_before"] == first["entries"][-1]["id"]
    rest = await record(locked, owner, before=first["next_before"])
    assert all(e["id"] < first["next_before"] for e in rest["entries"])


async def test_a_revoked_devices_entries_keep_its_name(locked) -> None:  # noqa: F811
    _, owner, _ = issue(locked, "Laptop")
    anna, anna_headers, _ = issue(locked, "Anna", abilities=only(Ability.COMMAND))
    await close(locked, anna_headers)
    await locked.delete(f"/api/auth/credentials/{anna.id}", headers=owner)
    [entry] = [
        e
        for e in (await record(locked, owner, actor=anna.id))["entries"]
        if e["action"] == "command"
    ]
    assert entry["actor"] == {
        "kind": "credential",
        "id": anna.id,
        "name": "Anna",
        "state": "revoked",
    }


async def test_an_observed_movement_is_not_a_command(locked) -> None:  # noqa: F811
    _, owner, _ = issue(locked)
    # Two reports within seconds of each other, far apart: somebody used a remote.
    for percent in (40, 70):
        response = await locked.post(
            "/api/sim/report", json={"shutter_id": "kueche", "percent": percent}, headers=owner
        )
        assert response.status_code == 200
    observed = [
        e for e in (await record(locked, owner))["entries"] if e["action"] == "movement_observed"
    ]
    assert observed and observed[0]["actor"]["kind"] == "bridge"
    assert observed[0]["shutter_id"] == "kueche"


async def test_an_automation_is_named_as_itself(locked) -> None:  # noqa: F811
    _, owner, _ = issue(locked)
    rule = (
        await locked.post(
            "/api/automations",
            json={
                "name": "Abends zu",
                "days": [True] * 7,
                "trigger": {"kind": "time", "time": "20:00"},
                "targets": ["kueche"],
                "action": {"kind": "close"},
            },
            headers=owner,
        )
    ).json()
    await locked.app.state.automation.run_due(datetime(2026, 9, 22, 20, 0, tzinfo=BERLIN))
    [entry] = [
        e
        for e in (await record(locked, owner, shutter="kueche"))["entries"]
        if e["action"] == "command"
    ]
    assert entry["actor"] == {"kind": "automation", "id": rule["id"], "name": "Abends zu"}


async def test_configuration_changes_are_recorded_once_and_only_when_they_happened(
    locked,  # noqa: F811
) -> None:
    _, owner, _ = issue(locked, "Laptop")
    await locked.put("/api/location", json={"latitude": 52.5, "longitude": 13.4}, headers=owner)
    await locked.put("/api/groups/g_nope", json={"name": "x", "members": ["kueche"]}, headers=owner)
    await locked.post("/api/groups", json={"name": "Unten", "members": ["kueche"]}, headers=owner)
    actions = [e["action"] for e in (await record(locked, owner))["entries"]]
    assert actions.count("location_changed") == 1
    assert actions.count("group_changed") == 1  # the 404 did not change anything


async def test_reading_the_record_needs_manage(locked) -> None:  # noqa: F811
    _, headers, _ = issue(locked, "Nur fahren", abilities=only(Ability.COMMAND))
    assert (await locked.get("/api/audit", headers=headers)).status_code == 403


async def test_retention(locked) -> None:  # noqa: F811
    from datetime import timedelta

    _, owner, _ = issue(locked)
    await close(locked, owner)
    audit = locked.app.state.audit
    later = audit.clock() + timedelta(days=181)
    assert audit.purge(later - timedelta(days=180)) >= 1
    assert (await record(locked, owner))["entries"] == []
