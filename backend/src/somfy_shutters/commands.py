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
        # Expressed as a level command at the current position: we only speak
        # level/cmd. See contracts/mqtt.md — this is an approximation, and
        # hardware bring-up has to confirm the motor halts crisply.
        await bridge.send_level(
            tracker.settings.shutters[shutter_id].address, tracker.halt_level(shutter_id)
        )
        await tracker.stop(shutter_id)
        return {"accepted": True, "movement": None}

    target = tracker.plan(shutter_id, kind, target_percent)
    assert target is not None
    level = tracker.level_for(shutter_id, target)
    await bridge.send_level(tracker.settings.shutters[shutter_id].address, level)
    movement = await tracker.start_movement(shutter_id, target, level)
    log.info("command %s on %s -> %s%%", action, shutter_id, target)
    return {"accepted": True, "movement": movement_json(movement)}
