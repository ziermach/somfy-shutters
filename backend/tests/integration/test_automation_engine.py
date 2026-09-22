"""T013: the engine against the simulated house, on a clock the test controls.

Nothing here sleeps. `run_due(now)` and `catch_up(now)` take the time as an
argument; the shutters are the simulator's, commanded through the same function a
button press uses.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from somfy_shutters.automation.clock import ClockGuard
from somfy_shutters.automation.engine import HEARTBEAT_KEY, AutomationEngine
from somfy_shutters.automation.models import FiringStatus, RuleDraft
from somfy_shutters.automation.store import AutomationStore
from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG

BERLIN = ZoneInfo("Europe/Berlin")
TUESDAY_0645 = datetime(2026, 9, 22, 6, 45, tzinfo=BERLIN)


class Runs:
    def __init__(self) -> None:
        self.measuring: set[str] = set()

    def is_measuring(self, shutter_id: str) -> bool:
        return shutter_id in self.measuring


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


@pytest.fixture
def house(tmp_path):
    settings = Settings.model_validate(CONFIG)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    with TestClient(app):
        store = AutomationStore(tmp_path / "state.db")
        events: list[dict] = []

        async def publish(event: dict) -> None:
            events.append(event)

        state = SimpleNamespace(
            tracker=app.state.tracker, bridge=bridge, runs=Runs(), pending_checks={}
        )
        clock = Clock(TUESDAY_0645 - timedelta(hours=1))
        engine = AutomationEngine(
            store, state, publish, guard=ClockGuard(lambda: True), clock=clock
        )
        yield SimpleNamespace(
            engine=engine,
            store=store,
            state=state,
            bridge=bridge,
            events=events,
            clock=clock,
            tracker=app.state.tracker,
        )
        store.close()


def add(house, time="06:45", targets="all", action=None, **over):
    body = {
        "name": over.pop("name", "Test"),
        "days": over.pop("days", [True] * 7),
        "trigger": over.pop("trigger", {"kind": "time", "time": time}),
        "targets": targets,
        "action": action or {"kind": "close"},
    }
    body.update(over)
    return house.store.create(RuleDraft.model_validate(body))


async def test_a_firing_happens_once_however_often_run_due_is_called(house) -> None:
    rule = add(house)
    first = await house.engine.run_due(TUESDAY_0645)
    again = await house.engine.run_due(TUESDAY_0645 + timedelta(seconds=30))
    assert [f.status for f in first] == [FiringStatus.FIRED]
    assert again == []
    assert len(house.store.firings(rule.id)) == 1


async def test_it_commands_every_target_through_the_ordinary_path(house) -> None:
    add(house)
    await house.engine.run_due(TUESDAY_0645)
    for shutter_id in ("wohnzimmer", "kueche", "schlafzimmer"):
        movement = house.tracker.movement(shutter_id)
        assert movement is not None and movement.target_percent == 0


async def test_only_its_targets_move(house) -> None:
    add(house, targets=["kueche"])
    await house.engine.run_due(TUESDAY_0645)
    assert house.tracker.movement("kueche") is not None
    assert house.tracker.movement("wohnzimmer") is None


async def test_same_minute_rules_run_in_creation_order_and_the_last_decides(house) -> None:
    add(house, targets=["kueche"], action={"kind": "position", "percent": 30}, name="erst")
    add(house, targets=["kueche"], action={"kind": "position", "percent": 70}, name="dann")
    fired = await house.engine.run_due(TUESDAY_0645)
    assert len(fired) == 2
    assert house.tracker.movement("kueche").target_percent == 70


async def test_a_shutter_under_measurement_is_skipped_and_the_rest_commanded(house) -> None:
    rule = add(house)
    house.state.runs.measuring.add("schlafzimmer")
    [firing] = await house.engine.run_due(TUESDAY_0645)
    assert firing.status is FiringStatus.PARTIAL
    skipped = [o for o in firing.outcomes if o.result == "skipped"]
    assert [(o.shutter_id, o.reason) for o in skipped] == [
        ("schlafzimmer", "measurement_in_progress")
    ]
    assert house.store.last_firing(rule.id).status is FiringStatus.PARTIAL


async def test_bridge_offline_fails_and_nothing_is_sent_later(house) -> None:
    add(house, targets=["kueche"])
    house.bridge.set_connected(False)
    [firing] = await house.engine.run_due(TUESDAY_0645)
    assert firing.status is FiringStatus.FAILED
    assert firing.outcomes[0].reason == "bridge_unreachable"

    house.bridge.set_connected(True)
    assert await house.engine.run_due(TUESDAY_0645 + timedelta(minutes=1)) == []
    assert house.tracker.movement("kueche") is None


async def test_a_removed_shutter_is_reported_not_fatal(house) -> None:
    add(house, targets=["kueche", "gibtsnicht"])
    [firing] = await house.engine.run_due(TUESDAY_0645)
    assert firing.status is FiringStatus.PARTIAL
    assert ("gibtsnicht", "removed") in [(o.shutter_id, o.reason) for o in firing.outcomes]


async def test_up_to_ten_minutes_late_it_still_fires(house) -> None:
    add(house)
    [firing] = await house.engine.run_due(TUESDAY_0645 + timedelta(minutes=4))
    assert firing.status is FiringStatus.FIRED
    assert firing.fired_at - firing.planned_at == timedelta(minutes=4)


async def test_restart_after_the_grace_records_missed_and_sends_nothing(house) -> None:
    rule = add(house)
    house.store.set_setting(HEARTBEAT_KEY, (TUESDAY_0645 - timedelta(minutes=5)).isoformat())
    restarted = TUESDAY_0645 + timedelta(minutes=15)
    house.engine.started_at = restarted
    recorded = await house.engine.catch_up(restarted)
    assert [f.status for f in recorded] == [FiringStatus.MISSED]
    assert house.tracker.movement("kueche") is None
    assert house.store.last_firing(rule.id).status is FiringStatus.MISSED


async def test_restart_within_the_grace_carries_it_out_once(house) -> None:
    rule = add(house)
    house.store.set_setting(HEARTBEAT_KEY, (TUESDAY_0645 - timedelta(minutes=1)).isoformat())
    restarted = TUESDAY_0645 + timedelta(minutes=4)
    house.engine.started_at = restarted
    recorded = await house.engine.catch_up(restarted)
    assert [f.status for f in recorded] == [FiringStatus.FIRED]
    assert len(house.store.firings(rule.id)) == 1


async def test_an_unreliable_clock_holds_and_records_held_afterwards(house) -> None:
    rule = add(house)
    house.store.set_setting(HEARTBEAT_KEY, (TUESDAY_0645 - timedelta(minutes=5)).isoformat())
    house.engine.guard.override = False
    await house.engine.check_clock(TUESDAY_0645 - timedelta(minutes=5))
    assert await house.engine.run_due(TUESDAY_0645) == []
    assert house.tracker.movement("kueche") is None

    house.engine.guard.override = None
    await house.engine.check_clock(TUESDAY_0645 + timedelta(minutes=20))
    assert house.store.last_firing(rule.id).status is FiringStatus.HELD
    assert house.tracker.movement("kueche") is None
    assert any(e["type"] == "automations" and e["clock_reliable"] is False for e in house.events)


async def test_every_firing_is_announced(house) -> None:
    add(house, name="Abends zu")
    await house.engine.run_due(TUESDAY_0645)
    fired = [e for e in house.events if e["type"] == "automation_fired"]
    assert fired and fired[0]["rule_name"] == "Abends zu" and fired[0]["commanded"] == 3


def test_reschedule_points_at_the_earliest_next_firing(house) -> None:
    add(house, time="07:30")
    add(house, time="06:45")
    assert house.engine.reschedule(TUESDAY_0645 - timedelta(hours=1)) == TUESDAY_0645


async def test_a_day_without_sunset_is_recorded_not_silent(house) -> None:
    """Only possible far north — but a rule that silently never fires is worse."""
    house.store.set_setting("location", {"latitude": 78.22, "longitude": 15.65})
    rule = add(house, trigger={"kind": "sunset", "offset_minutes": 0})
    midsummer_noon = datetime(2026, 6, 21, 12, 0, tzinfo=BERLIN)
    await house.engine.run_due(midsummer_noon)
    last = house.store.last_firing(rule.id)
    assert last is not None and last.status is FiringStatus.NO_SUN
    await house.engine.run_due(midsummer_noon + timedelta(hours=1))
    assert len(house.store.firings(rule.id)) == 1, "once per day, not once per wake-up"
