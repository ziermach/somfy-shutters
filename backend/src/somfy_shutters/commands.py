"""The one command path.

A button press, "Alle zu" and an automation all end up here, so every one of them
honours the same things: the measurement lock, the travel curve, the bridge's own
counter, the pending check, and the frames every client animates from. Moved out of
the REST layer for feature 003 without changing what it does.
"""

from __future__ import annotations

import logging
from typing import Any

from .api.serialize import movement_json
from .bridge.base import BridgeUnreachable
from .models import Action

log = logging.getLogger(__name__)


class MeasurementInProgress(RuntimeError):
    """A command was aimed at a shutter that is being measured (FR-028)."""


async def apply(
    state: Any, shutter_id: str, action: str, target_percent: int | None = None
) -> dict[str, Any]:
    """Issue one command.

    Raises MeasurementInProgress, BridgeUnreachable (from the bridge) or
    UnknownShutter (from the tracker). Nothing is queued: a command that cannot be
    handed over now did not happen.
    """
    # Checked here rather than on one route: "Alle zu" reached this function by
    # another path and drove straight through a running measurement.
    runs = getattr(state, "runs", None)
    if runs is not None and runs.is_measuring(shutter_id):
        raise MeasurementInProgress(shutter_id)

    tracker = state.tracker
    bridge = state.bridge
    kind = Action(action)
    # Driven somewhere else, the shutter no longer shows the check's midpoint;
    # an answer now would describe a position nobody asked about.
    getattr(state, "pending_checks", {}).pop(shutter_id, None)

    if kind is Action.STOP:
        # The bridge's explicit stop. Asking for the current position instead would do
        # nothing on current Pi-Somfy and let the shutter run on (feature 006).
        await bridge.send_stop(tracker.settings.shutters[shutter_id].address)
        await tracker.stop(shutter_id)
        return {"accepted": True, "movement": None}

    target = tracker.plan(shutter_id, kind, target_percent)
    assert target is not None
    level = tracker.level_for(shutter_id, target)
    await bridge.send_level(tracker.settings.shutters[shutter_id].address, level)
    movement = await tracker.start_movement(shutter_id, target, level)
    log.info("command %s on %s -> %s%%", action, shutter_id, target)
    return {"accepted": True, "movement": movement_json(movement)}


async def apply_many(
    state: Any, shutter_ids: list[str], action: str, target_percent: int | None = None
) -> list[dict[str, Any]]:
    """Issue one command to several shutters, one after another, in the order given.

    "Alle auf/zu", a group and an automation all come through here, so a partial
    failure means the same thing to each of them (specs/004-shutter-groups/research.md
    §3). Sequential on purpose: the radio sends one frame at a time anyway, and the
    order decides whose animation starts first. A shutter that cannot be commanded
    is reported and skipped; nothing is retried and nothing is queued.
    """
    results: list[dict[str, Any]] = []
    for shutter_id in shutter_ids:
        try:
            done = await apply(state, shutter_id, action, target_percent)
            results.append({"id": shutter_id, "accepted": True, "movement": done["movement"]})
        except MeasurementInProgress:
            results.append(
                {"id": shutter_id, "accepted": False, "error": "measurement_in_progress"}
            )
        except BridgeUnreachable:
            results.append({"id": shutter_id, "accepted": False, "error": "bridge_unreachable"})
    return results
