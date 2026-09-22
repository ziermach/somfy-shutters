"""The state push.

Every connect begins with a full snapshot (FR-020). There is no resume-from-
offset and no replay buffer: a client that reconnects after five minutes is in
exactly the same position as one connecting for the first time, which removes a
whole class of bug rather than solving it.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .serialize import movement_json, position_json, snapshot_json

log = logging.getLogger(__name__)

router = APIRouter()


class Hub:
    """Holds the open sockets and hands them frames."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._seq = 0

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    async def join(self, socket: WebSocket, snapshot: dict[str, Any]) -> None:
        await socket.accept()
        self._clients.add(socket)
        await socket.send_json({"type": "snapshot", "seq": self.next_seq(), "data": snapshot})

    def leave(self, socket: WebSocket) -> None:
        self._clients.discard(socket)

    async def broadcast(self, frame: dict[str, Any]) -> None:
        if not self._clients:
            return
        frame = {**frame, "seq": self.next_seq()}
        dead: list[WebSocket] = []
        for client in list(self._clients):
            try:
                await client.send_json(frame)
            except Exception:  # a client that vanished mid-send
                dead.append(client)
        for client in dead:
            self._clients.discard(client)

    @property
    def client_count(self) -> int:
        return len(self._clients)


def frame_for_event(event: dict[str, Any], tracker: Any) -> dict[str, Any] | None:
    """Translate a tracker event into the wire shape from contracts/websocket.md."""
    kind = event["type"]
    if kind == "movement":
        return {
            "type": "movement",
            "shutter_id": event["shutter_id"],
            "movement": movement_json(event["movement"]),
        }
    if kind in ("position", "correction"):
        frame = {
            "type": kind,
            "shutter_id": event["shutter_id"],
            "position": position_json(event["position"], tracker),
        }
        if kind == "correction":
            frame["ease_ms"] = event.get("ease_ms", 400)
        return frame
    if kind == "bridge":
        return {"type": "bridge", "connected": event["connected"], "kind": event["kind"]}
    if kind == "measuring":
        # A measurement started or ended. Every open client has to stop offering
        # buttons that the server would refuse anyway (FR-028).
        return {
            "type": "measuring",
            "shutter_id": event["shutter_id"],
            "active": event["active"],
            "direction": event.get("direction"),
        }
    if kind == "confirmable":
        # An offer, not a claim: the app has no idea whether it has arrived.
        return {
            "type": "confirmable",
            "shutter_id": event["shutter_id"],
            "direction": event["direction"],
            "name": event["name"],
        }
    if kind == "calibration":
        # Other clients are animating on the old timing until they hear this.
        return {
            "type": "calibration",
            "shutter_id": event["shutter_id"],
            "direction": event["direction"],
            "travel_seconds": event["travel_seconds"],
            "runs": event["runs"],
        }
    if kind in ("automations", "automation_fired"):
        # Feature 003. Already in wire shape: the engine builds them.
        return {k: v for k, v in event.items()}
    if kind == "groups":
        # Feature 004. The full list, never a delta: a client replaces its copy.
        return {"type": "groups", "groups": event["groups"]}
    if kind == "rules_changed":
        # No payload: a client showing the rules re-fetches them.
        return {"type": "rules_changed"}
    return None


@router.websocket("/api/ws")
async def websocket_endpoint(socket: WebSocket) -> None:
    app = socket.app
    hub: Hub = app.state.hub
    tracker = app.state.tracker
    bridge = app.state.bridge

    runs = getattr(app.state, "runs", None)
    snapshot = snapshot_json(tracker, bridge.kind, bridge.connected, runs)
    engine = getattr(app.state, "automation", None)
    if engine is not None:
        # In the snapshot rather than a frame after it, so the overview's banner
        # is right from the first frame (feature 003, FR-026).
        snapshot["automations"] = engine.state_json()
    groups = getattr(app.state, "groups", None)
    if groups is not None:
        snapshot["groups"] = [g.wire() for g in groups.groups()]  # feature 004
    await hub.join(socket, snapshot)
    try:
        while True:
            # Nothing is expected from the client; this keeps the socket open and
            # notices when it goes away. Commands travel over REST.
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.debug("websocket closed: %s", exc)
    finally:
        hub.leave(socket)
