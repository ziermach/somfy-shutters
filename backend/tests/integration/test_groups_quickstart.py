"""quickstart.md of feature 004, walked by machine (specs/004-shutter-groups/quickstart.md).

A and C go through the real HTTP surface; D drives the automation engine on a
clock the test controls, as feature 003's quickstart does. B is the overview and
is covered by frontend/src/lib/groups.test.ts and by hand.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from datetime import datetime, time, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from somfy_shutters.automation.models import FiringStatus
from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.groups import GroupDraft, GroupStore
from somfy_shutters.main import create_app
from somfy_shutters.models import utcnow
from somfy_shutters.store import Store

from ..conftest import CONFIG
from .test_automation_engine import BERLIN, TUESDAY_0645, add, house  # noqa: F401 — fixture


def house_of(n: int) -> Settings:
    return Settings.model_validate(
        {
            "general": {"stale_after_hours": 12, "default_travel_seconds": 20},
            "bridge": {"kind": "sim", "invert_level": False},
            "shutter": [
                {"id": f"s{i:02d}", "name": f"Fenster {i}", "address": f"0x2796{i:02d}"}
                for i in range(n)
            ],
        }
    )


@contextlib.asynccontextmanager
async def running(tmp_path, settings: Settings) -> AsyncIterator[AsyncClient]:
    """The app on the test's database; leaving the block is a shutdown."""
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
        app.router.lifespan_context(app),
    ):
        http.app = app  # type: ignore[attr-defined]
        yield http


def without(shutter_id: str) -> Settings:
    config = {**CONFIG, "shutter": [s for s in CONFIG["shutter"] if s["id"] != shutter_id]}
    return Settings.model_validate(config)


async def make(http: AsyncClient, name: str, *members: str) -> dict:
    response = await http.post("/api/groups", json={"name": name, "members": list(members)})
    assert response.status_code == 201, response.json()
    return response.json()


# --- A: groups -----------------------------------------------------------------


async def test_a3_groups_survive_a_restart(tmp_path) -> None:
    settings = Settings.model_validate(CONFIG)
    async with running(tmp_path, settings) as http:
        await make(http, "Erdgeschoss", "wohnzimmer", "kueche")
        await make(http, "Südseite", "wohnzimmer", "schlafzimmer")
        before = (await http.get("/api/groups")).json()
    async with running(tmp_path, settings) as http:
        assert (await http.get("/api/groups")).json() == before


async def test_a5_a_shutter_leaving_the_config_leaves_its_groups(tmp_path) -> None:
    async with running(tmp_path, Settings.model_validate(CONFIG)) as http:
        alone = await make(http, "Schlafen", "schlafzimmer")
        mixed = await make(http, "Mix", "kueche", "schlafzimmer")
    async with running(tmp_path, without("schlafzimmer")) as http:
        listed = {g["id"]: g for g in (await http.get("/api/groups")).json()["groups"]}
        assert listed[alone["id"]]["members"] == []  # kept, and says it is empty
        assert listed[mixed["id"]]["members"] == ["kueche"]
        response = await http.post(f"/api/groups/{alone['id']}/command", json={"action": "open"})
        assert response.status_code == 409
    async with running(tmp_path, Settings.model_validate(CONFIG)) as http:
        listed = {g["id"]: g for g in (await http.get("/api/groups")).json()["groups"]}
        assert listed[alone["id"]]["members"] == []  # back in the config, in no group


# --- C: group commands ---------------------------------------------------------------


async def test_c6_a_group_of_twelve_is_commanded_within_five_seconds(tmp_path) -> None:
    """FR-021 / SC-003: from the tap to the last member's command."""
    ids = [f"s{i:02d}" for i in range(12)]
    async with running(tmp_path, house_of(12)) as http:
        group = await make(http, "Alle zwölf", *ids)
        for sid in ids:  # all open first, so "zu" is a movement for every one
            await http.post("/api/sim/report", json={"shutter_id": sid, "percent": 100})
        tapped = utcnow()
        response = await http.post(f"/api/groups/{group['id']}/command", json={"action": "close"})
    assert response.status_code == 200
    started = [
        datetime.fromisoformat(r["movement"]["started_at"]) for r in response.json()["results"]
    ]
    assert len(started) == 12
    assert (max(started) - tapped).total_seconds() < 5


# --- D: automations ----------------------------------------------------------------


@pytest.fixture
def grouped(house, tmp_path):  # noqa: F811
    """The engine of feature 003's quickstart, now with groups and a counted radio."""
    store = GroupStore(tmp_path / "groups.db")
    house.engine.groups = store
    house.groups = store
    house.sent = []
    real = house.bridge.send_level

    async def counted(address: str, percent: int) -> None:
        await real(address, percent)
        house.sent.append(address)

    house.bridge.send_level = counted
    yield house
    store.close()


def group(home, name: str, *members: str) -> str:
    return home.groups.create(GroupDraft(name=name, members=list(members))).id


async def test_d1_a_group_target_reaches_its_members_and_says_so(grouped) -> None:
    eg = group(grouped, "Erdgeschoss", "wohnzimmer", "kueche")
    rule = add(grouped, targets={"groups": [eg]})
    await grouped.engine.run_due(TUESDAY_0645)
    [firing] = grouped.store.firings(rule.id)
    assert {o.shutter_id: o.via for o in firing.outcomes} == {
        "wohnzimmer": ["Erdgeschoss"],
        "kueche": ["Erdgeschoss"],
    }
    assert grouped.tracker.movement("schlafzimmer") is None


async def test_d2_membership_follows_without_editing_the_rule(grouped) -> None:
    eg = group(grouped, "Erdgeschoss", "wohnzimmer")
    rule = add(grouped, targets={"groups": [eg]})
    await grouped.engine.run_due(TUESDAY_0645)
    grouped.groups.update(eg, GroupDraft(name="Erdgeschoss", members=["wohnzimmer", "kueche"]))
    await grouped.engine.run_due(TUESDAY_0645 + timedelta(days=1))
    latest = grouped.store.firings(rule.id)[0]
    assert {o.shutter_id for o in latest.outcomes} == {"wohnzimmer", "kueche"}


async def test_d3_a_shutter_in_two_target_groups_is_commanded_once(grouped) -> None:
    eg = group(grouped, "Erdgeschoss", "wohnzimmer", "kueche")
    sued = group(grouped, "Südseite", "wohnzimmer", "schlafzimmer")
    rule = add(grouped, targets={"groups": [eg, sued]})
    await grouped.engine.run_due(TUESDAY_0645)
    [firing] = grouped.store.firings(rule.id)
    wz = [o for o in firing.outcomes if o.shutter_id == "wohnzimmer"]
    assert len(wz) == 1 and wz[0].via == ["Erdgeschoss", "Südseite"]
    assert len(grouped.sent) == len(set(grouped.sent)) == 3


async def test_d4_a_rule_whose_only_group_is_deleted_will_not_fire(grouped) -> None:
    sued = group(grouped, "Südseite", "wohnzimmer")
    rule = add(grouped, targets={"groups": [sued]})
    grouped.groups.delete(sued)
    assert grouped.store.drop_group(sued) is True
    stored = grouped.store.rule(rule.id)
    assert grouped.engine.next_for(stored, TUESDAY_0645 - timedelta(hours=1)).reason == "no_targets"
    assert await grouped.engine.run_due(TUESDAY_0645) == []
    assert grouped.sent == []
    assert grouped.store.firings(rule.id) == []  # not a "failed" firing: it never fires


async def test_d7_a_rule_stored_by_feature_003_still_fires(grouped) -> None:
    rule = add(grouped, targets=["kueche"])
    with grouped.store._lock:  # the row exactly as feature 003 wrote it
        grouped.store._conn.execute(
            "UPDATE automation_rule SET targets = ? WHERE id = ?", (json.dumps(["kueche"]), rule.id)
        )
    await grouped.engine.run_due(TUESDAY_0645)
    [firing] = grouped.store.firings(rule.id)
    assert firing.status is FiringStatus.FIRED
    assert [(o.shutter_id, o.via) for o in firing.outcomes] == [("kueche", [])]


async def test_sc005_a_simulated_month_commands_no_shutter_twice_per_firing(grouped) -> None:
    """Three rules whose group targets overlap, every day for 30 days."""
    eg = group(grouped, "Erdgeschoss", "wohnzimmer", "kueche")
    sued = group(grouped, "Südseite", "wohnzimmer", "schlafzimmer")
    alle = group(grouped, "Alle", "wohnzimmer", "kueche", "schlafzimmer")
    times = ["06:45", "12:00", "20:00"]
    add(grouped, time=times[0], targets={"groups": [eg, sued]}, name="Morgens")
    add(
        grouped,
        time=times[1],
        targets={"shutters": ["kueche"], "groups": [eg, alle]},
        name="Mittags",
    )
    add(grouped, time=times[2], targets={"groups": [sued, alle]}, name="Abends")
    firings = 0
    for day in range(30):
        for at in times:
            hour, minute = map(int, at.split(":"))
            now = datetime.combine(
                TUESDAY_0645.date() + timedelta(days=day), time(hour, minute), tzinfo=BERLIN
            )
            grouped.sent.clear()
            [done] = await grouped.engine.run_due(now)
            shutters = [o.shutter_id for o in done.outcomes]
            assert len(shutters) == len(set(shutters))
            assert len(grouped.sent) == len(set(grouped.sent)) == done.commanded
            firings += 1
    assert firings == 90
