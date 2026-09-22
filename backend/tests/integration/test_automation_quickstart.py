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
