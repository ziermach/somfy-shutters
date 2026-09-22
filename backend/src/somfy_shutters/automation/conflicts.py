"""Two rules that command the same shutter in the same minute, differently (FR-022).

Checked over a year of planned firings, because sun rules drift: two rules can meet
only in June. The later one in FR-011 order is carried out last, so it wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

from .models import Rule, RuleDraft
from .planner import SunLookup, firings_between

HORIZON = timedelta(days=366)
THIS = "this"
"""The winner when it is the rule being edited or created, which has no id yet."""


@dataclass(frozen=True)
class Conflict:
    rule_id: str
    rule_name: str
    shutter_id: str
    first_at: datetime
    winner: str


def _targets(targets: object, configured: list[str]) -> list[str]:
    if targets == "all":
        return configured
    return [sid for sid in configured if sid in targets]  # type: ignore[operator]


def find_conflicts(
    draft: RuleDraft,
    rules: list[Rule],
    configured: list[str],
    now: datetime,
    tz: tzinfo,
    sun: SunLookup | None,
    *,
    editing: str | None = None,
    created_at: datetime | None = None,
) -> list[Conflict]:
    if not draft.enabled:
        return []
    mine = set(firings_between(draft, now, now + HORIZON, tz, sun))
    if not mine:
        return []
    my_targets = _targets(draft.targets, configured)
    # A new rule is created now, so it sorts after every existing one.
    my_key = (created_at or now, editing or "~")
    found = []
    for other in rules:
        if other.id == editing or not other.enabled:
            continue
        if other.action.same_effect(draft.action):
            continue
        shared = [sid for sid in _targets(other.targets, configured) if sid in my_targets]
        if not shared:
            continue
        together = mine & set(firings_between(other, now, now + HORIZON, tz, sun))
        if not together:
            continue
        other_first = (other.created_at, other.id) < my_key
        found.append(
            Conflict(
                rule_id=other.id,
                rule_name=other.name,
                shutter_id=shared[0],
                first_at=min(together),
                winner=(editing or THIS) if other_first else other.id,
            )
        )
    return found
