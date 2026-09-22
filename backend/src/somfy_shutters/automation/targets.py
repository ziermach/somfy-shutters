"""Who a rule reaches (specs/004-shutter-groups/data-model.md, "Resolution").

One function, used by the engine when a rule fires, by the conflict check and by
the form's preview — so the warning and the firing can never disagree about which
shutters a rule means.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from ..groups import Group
from .models import RuleTargets


@dataclass(frozen=True)
class Resolution:
    reached: list[str]
    """Configured shutters, each once, in configuration order."""
    via: dict[str, list[str]] = field(default_factory=dict)
    """shutter id -> names of the listed groups it is a member of. Absent: direct."""
    removed: list[str] = field(default_factory=list)
    """Directly listed shutters no longer configured (feature 003's `removed`)."""


def resolve(
    targets: RuleTargets, configured: list[str], groups: Iterable[Group] = ()
) -> Resolution:
    """Group membership is read now, at this call (FR-023); unknown group ids are
    ignored, so a rule left pointing at a deleted group still behaves (research §6)."""
    if targets == "all":
        return Resolution(reached=list(configured))
    known = {g.id: g for g in groups}
    via: dict[str, list[str]] = {}
    for group_id in targets.groups:  # type: ignore[union-attr]
        group = known.get(group_id)
        if group is None:
            continue
        for shutter_id in group.members:
            via.setdefault(shutter_id, []).append(group.name)
    wanted = set(targets.shutters) | set(via)  # type: ignore[union-attr]
    return Resolution(
        reached=[sid for sid in configured if sid in wanted],
        via={sid: names for sid, names in via.items() if sid in configured},
        removed=[sid for sid in targets.shutters if sid not in configured],  # type: ignore[union-attr]
    )
