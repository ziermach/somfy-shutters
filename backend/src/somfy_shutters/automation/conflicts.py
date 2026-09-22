"""Two rules that command the same shutter in the same minute, differently (FR-022).

Checked over a year of planned firings, because sun rules drift: two rules can meet
only in June. The later one in FR-011 order is carried out last, so it wins.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

from ..groups import Group
from .models import Rule, RuleDraft
from .planner import SunLookup, firings_between
from .targets import resolve

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
    via: str | None = None
    """The group through which the rule being saved reaches the shared shutter."""


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
    groups: Iterable[Group] = (),
) -> list[Conflict]:
    if not draft.enabled:
        return []
    mine = set(firings_between(draft, now, now + HORIZON, tz, sun))
    if not mine:
        return []
    groups = list(groups)
    mine_resolved = resolve(draft.targets, configured, groups)
    my_targets = mine_resolved.reached
    # A new rule is created now, so it sorts after every existing one.
    my_key = (created_at or now, editing or "~")
    found = []
    for other in rules:
        if other.id == editing or not other.enabled:
            continue
        if other.action.same_effect(draft.action):
            continue
        shared = [
            sid for sid in resolve(other.targets, configured, groups).reached if sid in my_targets
        ]
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
                via=(mine_resolved.via.get(shared[0]) or [None])[0],
            )
        )
    return found


@dataclass(frozen=True)
class PairConflict:
    """Two stored rules that meet on a shutter (feature 004, FR-028)."""

    rule_id: str
    rule_name: str
    other_rule_id: str
    other_rule_name: str
    shutter_id: str
    via: str | None
    first_at: datetime
    winner: str


def conflicts_from_group_change(
    group_id: str,
    before: list[Group],
    after: list[Group],
    rules: list[Rule],
    configured: list[str],
    now: datetime,
    tz: tzinfo,
    sun: SunLookup | None,
) -> list[PairConflict]:
    """Conflicts between enabled rules that a change to one group created.

    Only pairs that meet with the new membership and did not with the old one: a
    clash the household already lived with is not news. Each rule pair is reported
    once, however many of its rules target the group.
    """

    def meeting(rule: Rule, groups: list[Group]) -> dict[str, Conflict]:
        return {
            c.rule_id: c
            for c in find_conflicts(
                rule,
                rules,
                configured,
                now,
                tz,
                sun,
                editing=rule.id,
                created_at=rule.created_at,
                groups=groups,
            )
        }

    names = {r.id: r.name for r in rules}
    seen: set[frozenset[str]] = set()
    found = []
    for rule in rules:
        if not rule.enabled or rule.targets == "all" or group_id not in rule.targets.groups:  # type: ignore[union-attr]
            continue
        old = meeting(rule, before)
        for other_id, c in meeting(rule, after).items():
            pair = frozenset((rule.id, other_id))
            if other_id in old or pair in seen:
                continue
            seen.add(pair)
            found.append(
                PairConflict(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    other_rule_id=other_id,
                    other_rule_name=names[other_id],
                    shutter_id=c.shutter_id,
                    via=c.via,
                    first_at=c.first_at,
                    winner=c.winner,
                )
            )
    return found
