"""quickstart.md, walked by machine (feature 003).

Each test is one scenario from specs/003-shutter-automations/quickstart.md, on a
clock the test controls. A1 is also worth doing once by hand in the browser.
"""

from __future__ import annotations

from datetime import timedelta

from somfy_shutters.automation.models import FiringStatus
from somfy_shutters.models import Confidence

from .test_automation_engine import TUESDAY_0645, add, house  # noqa: F401 — fixture

# --- A: schedules ------------------------------------------------------------


async def test_a1_it_fires_with_nobody_watching(house) -> None:  # noqa: F811
    """No WebSocket client is connected in this fixture; the engine does not need one."""
    rule = add(house, targets=["kueche"])
    await house.engine.run_due(TUESDAY_0645)
    assert house.tracker.movement("kueche").target_percent == 0
    last = house.store.last_firing(rule.id)
    assert last.status is FiringStatus.FIRED and last.commanded == 1


async def test_a2_the_wrong_weekday_does_nothing(house) -> None:  # noqa: F811
    tomorrow_only = [False] * 7
    tomorrow_only[TUESDAY_0645.weekday() + 1] = True
    rule = add(house, days=tomorrow_only)
    assert await house.engine.run_due(TUESDAY_0645) == []
    nxt = house.engine.next_for(rule, TUESDAY_0645)
    assert nxt.at == TUESDAY_0645 + timedelta(days=1)


async def test_a3_only_its_targets(house) -> None:  # noqa: F811
    add(house, targets=["wohnzimmer", "kueche"])
    await house.engine.run_due(TUESDAY_0645)
    assert house.tracker.movement("wohnzimmer") is not None
    assert house.tracker.movement("kueche") is not None
    assert house.tracker.movement("schlafzimmer") is None


async def test_a4_a_position_is_an_estimate(house) -> None:  # noqa: F811
    add(house, targets=["wohnzimmer"], action={"kind": "position", "percent": 30})
    await house.engine.run_due(TUESDAY_0645)
    movement = house.tracker.movement("wohnzimmer")
    assert movement.target_percent == 30
    assert house.tracker.position("wohnzimmer").confidence is Confidence.ESTIMATED


# --- E: the edges that matter ------------------------------------------------

from datetime import datetime  # noqa: E402

from somfy_shutters.automation.clock import ClockGuard  # noqa: E402
from somfy_shutters.automation.engine import HEARTBEAT_KEY, AutomationEngine  # noqa: E402

from .test_automation_engine import BERLIN  # noqa: E402


async def test_e1_restart_within_the_grace_fires_late_once(house) -> None:  # noqa: F811
    rule = add(house)
    house.store.set_setting(HEARTBEAT_KEY, (TUESDAY_0645 - timedelta(minutes=1)).isoformat())
    back = TUESDAY_0645 + timedelta(minutes=4)
    house.engine.started_at = back
    [firing] = await house.engine.catch_up(back)
    assert firing.status is FiringStatus.FIRED
    assert (firing.planned_at, firing.fired_at) == (TUESDAY_0645, back)
    assert len(house.store.firings(rule.id)) == 1


async def test_e2_restart_after_the_grace_is_missed(house) -> None:  # noqa: F811
    rule = add(house, targets=["kueche"])
    house.store.set_setting(HEARTBEAT_KEY, (TUESDAY_0645 - timedelta(minutes=1)).isoformat())
    back = TUESDAY_0645 + timedelta(minutes=15)
    house.engine.started_at = back
    await house.engine.catch_up(back)
    assert house.store.last_firing(rule.id).status is FiringStatus.MISSED
    assert house.tracker.movement("kueche") is None


async def test_e3_an_unreliable_clock_holds_and_says_so(house) -> None:  # noqa: F811
    rule = add(house, targets=["kueche"])
    house.store.set_setting(HEARTBEAT_KEY, (TUESDAY_0645 - timedelta(minutes=2)).isoformat())
    house.engine.guard.override = False
    await house.engine.check_clock(TUESDAY_0645 - timedelta(minutes=1))
    assert house.engine.state_json()["clock_reliable"] is False
    await house.engine.run_due(TUESDAY_0645)
    house.engine.guard.override = None
    await house.engine.check_clock(TUESDAY_0645 + timedelta(minutes=20))
    assert house.store.last_firing(rule.id).status is FiringStatus.HELD
    assert house.tracker.movement("kueche") is None


async def test_e4_daylight_saving_days(house) -> None:  # noqa: F811
    rule = add(house, time="02:30", targets=["kueche"])
    spring = datetime(2026, 3, 29, 3, 0, tzinfo=BERLIN)
    [firing] = await house.engine.run_due(spring)
    assert firing.planned_at == spring, "02:30 does not exist; the first valid minute is 03:00"

    autumn_first = datetime(2026, 10, 25, 2, 30, tzinfo=BERLIN, fold=0)
    autumn_second = datetime(2026, 10, 25, 2, 30, tzinfo=BERLIN, fold=1)
    fired = await house.engine.run_due(autumn_first)
    fired += await house.engine.run_due(autumn_second)
    fired += await house.engine.run_due(autumn_second + timedelta(minutes=5))
    assert len(fired) == 1, "02:30 happens twice; the rule fires once"
    assert len(house.store.firings(rule.id)) == 2


async def test_e5_no_double_firing_across_a_restart(house) -> None:  # noqa: F811
    rule = add(house, targets=["kueche"])
    await house.engine.run_due(TUESDAY_0645)
    await house.engine.run_due(TUESDAY_0645)
    house.engine.beat(TUESDAY_0645)

    async def publish(event: dict) -> None:
        pass

    restarted = AutomationEngine(
        house.store,
        house.state,
        publish,
        guard=ClockGuard(lambda: True),
        clock=lambda: TUESDAY_0645 + timedelta(seconds=1),
    )
    assert await restarted.catch_up(TUESDAY_0645 + timedelta(seconds=1)) == []
    assert len(house.store.firings(rule.id)) == 1


async def test_e6_bridge_down_fails_and_does_not_queue(house) -> None:  # noqa: F811
    rule = add(house, targets=["kueche"])
    house.bridge.set_connected(False)
    await house.engine.run_due(TUESDAY_0645)
    last = house.store.last_firing(rule.id)
    assert last.status is FiringStatus.FAILED
    assert last.outcomes[0].reason == "bridge_unreachable"
    house.bridge.set_connected(True)
    await house.engine.run_due(TUESDAY_0645 + timedelta(minutes=2))
    assert house.tracker.movement("kueche") is None
