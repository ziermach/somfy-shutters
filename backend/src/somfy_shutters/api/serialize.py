"""One place that turns state into JSON.

REST and the WebSocket must not drift apart — contracts/rest.md defines the
shutter shape and contracts/websocket.md reuses it, so the code does too.
"""

from __future__ import annotations

from typing import Any

from ..models import Movement, PositionEstimate
from ..tracker import Tracker


def position_json(position: PositionEstimate, tracker: Tracker) -> dict[str, Any]:
    age = position.age_seconds(tracker._clock())
    return {
        "percent": position.percent,
        "confidence": position.confidence.value,
        "certain_at": position.certain_at.isoformat() if position.certain_at else None,
        "age_seconds": None if age is None else round(age),
        "stale": position.is_stale(tracker.settings.general.stale_after_hours, tracker._clock()),
        "source": position.source.value,
    }


def movement_json(movement: Movement | None) -> dict[str, Any] | None:
    if movement is None:
        return None
    return {
        "from_percent": movement.from_percent,
        "target_percent": movement.target_percent,
        "direction": movement.direction.value,
        "started_at": movement.started_at.isoformat(),
        "expected_arrival": movement.expected_arrival.isoformat(),
        "origin": movement.origin.value,
    }


def shutter_json(shutter_id: str, tracker: Tracker) -> dict[str, Any]:
    config = tracker.settings.shutters[shutter_id]
    return {
        "id": config.id,
        "name": config.name,
        "calibrated": config.calibrated,
        "travel_up_seconds": config.travel_up_seconds,
        "travel_down_seconds": config.travel_down_seconds,
        "position": position_json(tracker.position(shutter_id), tracker),
        "movement": movement_json(tracker.movement(shutter_id)),
    }


def snapshot_json(tracker: Tracker, bridge_kind: str, connected: bool) -> dict[str, Any]:
    return {
        "shutters": [shutter_json(sid, tracker) for sid in tracker.settings.shutters],
        "bridge": {"connected": connected, "kind": bridge_kind},
    }
