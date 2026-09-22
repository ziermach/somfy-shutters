"""T008: the store round-trips rules, and the firing table refuses a second firing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from somfy_shutters.automation.models import Firing, FiringStatus, Outcome, RuleDraft
from somfy_shutters.automation.store import AutomationStore

SHAPES = [
    {"kind": "time", "time": "06:45"},
    {"kind": "sunset", "offset_minutes": -30, "not_before": None, "not_after": "21:00"},
    {"kind": "sunrise", "offset_minutes": 15, "not_before": "06:30", "not_after": None},
]
ACTIONS = [{"kind": "open"}, {"kind": "close"}, {"kind": "position", "percent": 30}]


@pytest.fixture
def store(tmp_path):
    s = AutomationStore(tmp_path / "state.db")
    yield s
    s.close()


def draft(trigger=SHAPES[0], action=ACTIONS[0], targets="all", **over) -> RuleDraft:
    body = {
        "name": "Test",
        "days": [True, False, True, False, True, False, True],
        "trigger": trigger,
        "targets": targets,
        "action": action,
    }
    body.update(over)
    return RuleDraft.model_validate(body)


@pytest.mark.parametrize("trigger", SHAPES)
@pytest.mark.parametrize("action", ACTIONS)
def test_every_rule_shape_round_trips(store, trigger, action) -> None:
    original = draft(trigger, action, targets=["wohnzimmer", "kueche"])
    stored = store.create(original)
    back = store.rule(stored.id)
    assert back is not None
    assert (
        RuleDraft.model_validate(back.model_dump(include=set(RuleDraft.model_fields))) == original
    )


def test_rules_come_back_in_creation_order(store) -> None:
    t0 = datetime(2026, 9, 22, tzinfo=UTC)
    ids = [store.create(draft(name=f"R{i}"), now=t0 + timedelta(seconds=i)).id for i in range(3)]
    assert [r.id for r in store.rules()] == ids


def test_a_second_firing_for_the_same_instant_is_refused(store) -> None:
    rule = store.create(draft())
    at = datetime(2026, 9, 22, 6, 45, tzinfo=timezone(timedelta(hours=2)))
    first = Firing(rule_id=rule.id, planned_at=at, status=FiringStatus.FIRED)
    assert store.record_firing(first) is True
    # the same instant, spelled in UTC this time
    again = Firing(rule_id=rule.id, planned_at=at.astimezone(UTC), status=FiringStatus.FIRED)
    assert store.record_firing(again) is False


def test_finishing_a_firing_stores_its_outcomes(store) -> None:
    rule = store.create(draft())
    at = datetime(2026, 9, 22, 4, 45, tzinfo=UTC)
    store.record_firing(Firing(rule_id=rule.id, planned_at=at, status=FiringStatus.FIRED))
    outcomes = [
        Outcome(shutter_id="wohnzimmer", result="commanded"),
        Outcome(shutter_id="kueche", result="skipped", reason="measurement_in_progress"),
    ]
    store.finish_firing(
        Firing(
            rule_id=rule.id,
            planned_at=at,
            fired_at=at,
            status=FiringStatus.PARTIAL,
            outcomes=outcomes,
        )
    )
    last = store.last_firing(rule.id)
    assert last is not None and last.status is FiringStatus.PARTIAL
    assert last.outcomes == outcomes


def test_deleting_a_rule_deletes_its_firings(store) -> None:
    rule = store.create(draft())
    store.record_firing(
        Firing(
            rule_id=rule.id,
            planned_at=datetime(2026, 9, 22, tzinfo=UTC),
            status=FiringStatus.MISSED,
        )
    )
    assert store.delete(rule.id)
    assert store.firings(rule.id) == []


def test_purge_keeps_recent_firings(store) -> None:
    rule = store.create(draft())
    now = datetime(2026, 9, 22, tzinfo=UTC)
    for days in (1, 89, 91, 200):
        store.record_firing(
            Firing(
                rule_id=rule.id, planned_at=now - timedelta(days=days), status=FiringStatus.FIRED
            )
        )
    assert store.purge_before(now - timedelta(days=90)) == 2
    assert len(store.firings(rule.id)) == 2


def test_settings_round_trip_and_delete(store) -> None:
    store.set_setting("location", {"latitude": 52.52, "longitude": 13.4})
    assert store.setting("location") == {"latitude": 52.52, "longitude": 13.4}
    store.set_setting("location", None)
    assert store.setting("location") is None
