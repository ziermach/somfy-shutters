"""T034: the conflict warning finds what it should, and nothing else."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from somfy_shutters.automation.conflicts import THIS, find_conflicts
from somfy_shutters.automation.models import Rule, RuleDraft
from somfy_shutters.automation.sun import sun_lookup

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 1, 5, 12, 0, tzinfo=BERLIN)
SHUTTERS = ["wohnzimmer", "kueche"]
SUN = sun_lookup(52.52, 13.40, BERLIN)


def draft(trigger=None, action=None, targets="all", **over) -> RuleDraft:
    body = {
        "name": over.pop("name", "Neu"),
        "days": over.pop("days", [True] * 7),
        "trigger": trigger or {"kind": "time", "time": "07:00"},
        "targets": targets,
        "action": action or {"kind": "open"},
    }
    body.update(over)
    return RuleDraft.model_validate(body)


def existing(rule_id="r_old", created=NOW - timedelta(days=30), **kw) -> Rule:
    d = draft(**kw)
    return Rule(
        **d.model_dump(), id=rule_id, created_at=created.astimezone(UTC), updated_at=created
    )


def test_same_minute_different_action_conflicts_and_the_newer_rule_wins() -> None:
    old = existing(action={"kind": "close"}, name="Alt")
    [c] = find_conflicts(draft(), [old], SHUTTERS, NOW, BERLIN, None)
    assert c.rule_id == "r_old" and c.rule_name == "Alt"
    assert c.shutter_id == "wohnzimmer"
    assert c.winner == THIS
    assert c.first_at.astimezone(BERLIN).strftime("%H:%M") == "07:00"


def test_editing_an_older_rule_lets_the_newer_one_win() -> None:
    newer = existing("r_new", created=NOW - timedelta(days=1), action={"kind": "close"})
    [c] = find_conflicts(
        draft(),
        [newer],
        SHUTTERS,
        NOW,
        BERLIN,
        None,
        editing="r_edit",
        created_at=NOW - timedelta(days=60),
    )
    assert c.winner == "r_new"


def test_same_action_is_no_conflict() -> None:
    assert find_conflicts(draft(), [existing()], SHUTTERS, NOW, BERLIN, None) == []


def test_different_shutters_is_no_conflict() -> None:
    old = existing(action={"kind": "close"}, targets=["kueche"])
    assert find_conflicts(draft(targets=["wohnzimmer"]), [old], SHUTTERS, NOW, BERLIN, None) == []


def test_a_disabled_rule_is_no_conflict() -> None:
    old = existing(action={"kind": "close"}, enabled=False)
    assert find_conflicts(draft(), [old], SHUTTERS, NOW, BERLIN, None) == []


def test_a_rule_never_conflicts_with_itself_when_edited() -> None:
    old = existing("r_self", action={"kind": "close"})
    assert find_conflicts(draft(), [old], SHUTTERS, NOW, BERLIN, None, editing="r_self") == []


def test_two_rules_that_meet_only_in_summer_are_found() -> None:
    """Sunset bounded to 21:00 meets a fixed 21:00 rule only on long June evenings."""
    sunset = draft(
        trigger={"kind": "sunset", "offset_minutes": 0, "not_before": None, "not_after": "21:00"},
        action={"kind": "close"},
    )
    evening = existing(
        trigger={"kind": "time", "time": "21:00"}, action={"kind": "position", "percent": 40}
    )
    [c] = find_conflicts(sunset, [evening], SHUTTERS, NOW, BERLIN, SUN)
    assert c.first_at.month in (5, 6, 7)
