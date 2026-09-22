"""Commands and queries.

A command is a one-shot request that wants a status code and a message a person
can read; state comes back over the WebSocket instead. Errors share one shape so
the client has a single code path.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..bridge.base import BridgeUnreachable
from ..models import Action
from ..tracker import Tracker, UnknownShutter
from .serialize import movement_json, shutter_json, snapshot_json

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

BRIDGE_UNREACHABLE = {
    "error": "bridge_unreachable",
    "message": "Der Befehl konnte nicht zugestellt werden. Die Funkbrücke antwortet nicht.",
    "detail": None,
}


class CommandBody(BaseModel):
    action: Literal["open", "close", "stop", "position"]
    target_percent: int | None = Field(default=None, ge=0, le=100)


def _tracker(request: Request) -> Tracker:
    return request.app.state.tracker


class MeasurementInProgress(RuntimeError):
    """A command was aimed at a shutter that is being measured (FR-028)."""


async def _apply(request: Request, shutter_id: str, body: CommandBody) -> dict[str, Any]:
    """Issue one command. Raises BridgeUnreachable if it could not be handed over."""
    # Checked here rather than on one route: "Alle zu" reached this function by
    # another path and drove straight through a running measurement.
    runs = getattr(request.app.state, "runs", None)
    if runs is not None and runs.is_measuring(shutter_id):
        raise MeasurementInProgress(shutter_id)

    tracker: Tracker = request.app.state.tracker
    bridge = request.app.state.bridge
    action = Action(body.action)
    # Driven somewhere else, the shutter no longer shows the check's midpoint;
    # an answer now would describe a position nobody asked about.
    getattr(request.app.state, "pending_checks", {}).pop(shutter_id, None)

    if action is Action.STOP:
        # Expressed as a level command at the current position: we only speak
        # level/cmd. See contracts/mqtt.md — this is an approximation, and
        # hardware bring-up has to confirm the motor halts crisply.
        await bridge.send_level(
            tracker.settings.shutters[shutter_id].address, tracker.halt_level(shutter_id)
        )
        await tracker.stop(shutter_id)
        return {"accepted": True, "movement": None}

    target = tracker.plan(shutter_id, action, body.target_percent)
    assert target is not None
    level = tracker.level_for(shutter_id, target)
    await bridge.send_level(tracker.settings.shutters[shutter_id].address, level)
    movement = await tracker.start_movement(shutter_id, target, level)
    log.info("command %s on %s -> %s%%", body.action, shutter_id, target)
    return {"accepted": True, "movement": movement_json(movement)}


@router.get("/shutters")
async def list_shutters(request: Request) -> dict[str, Any]:
    bridge = request.app.state.bridge
    return snapshot_json(
        _tracker(request), bridge.kind, bridge.connected, getattr(request.app.state, "runs", None)
    )


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    bridge = request.app.state.bridge
    tracker = _tracker(request)
    # 'ok' even when the bridge is down: the service is up and correctly
    # reporting a broken dependency. Conflating the two makes this useless.
    return {
        "status": "ok",
        "bridge": {"connected": bridge.connected, "kind": bridge.kind},
        "shutters": len(tracker.settings.shutters),
    }


@router.post("/shutters/command")
async def command_all(request: Request, body: CommandBody) -> JSONResponse:
    tracker = _tracker(request)
    results: list[dict[str, Any]] = []
    for shutter_id in tracker.settings.shutters:
        try:
            await _apply(request, shutter_id, body)
            results.append({"id": shutter_id, "accepted": True})
        except MeasurementInProgress:
            # The others still move; this one is left alone and the reason is said.
            results.append(
                {"id": shutter_id, "accepted": False, "error": "measurement_in_progress"}
            )
        except BridgeUnreachable:
            results.append({"id": shutter_id, "accepted": False, "error": "bridge_unreachable"})
    accepted = sum(1 for r in results if r["accepted"])
    status = 200 if accepted == len(results) else 503 if accepted == 0 else 207
    return JSONResponse({"results": results}, status_code=status)


@router.post("/shutters/{shutter_id}/command")
async def command_one(request: Request, shutter_id: str, body: CommandBody) -> JSONResponse:
    tracker = _tracker(request)
    if shutter_id not in tracker.settings.shutters:
        raise HTTPException(
            404,
            detail={
                "error": "unknown_shutter",
                "message": f"Kein Rolladen {shutter_id!r}.",
                "detail": None,
            },
        )
    if body.action == "position" and body.target_percent is None:
        raise HTTPException(
            422,
            detail={
                "error": "target_required",
                "message": "Für 'position' fehlt target_percent.",
                "detail": None,
            },
        )
    try:
        return JSONResponse(await _apply(request, shutter_id, body))
    except MeasurementInProgress:
        return JSONResponse(
            {
                "accepted": False,
                "error": "measurement_in_progress",
                "message": "Für diesen Rolladen läuft gerade eine Messung.",
                "detail": None,
            },
            status_code=409,
        )
    except BridgeUnreachable:
        return JSONResponse({"accepted": False, **BRIDGE_UNREACHABLE}, status_code=503)
    except UnknownShutter:
        raise HTTPException(
            404,
            detail={
                "error": "unknown_shutter",
                "message": f"Kein Rolladen {shutter_id!r}.",
                "detail": None,
            },
        ) from None


@router.post("/shutters/{shutter_id}/resync")
async def resync(request: Request, shutter_id: str) -> JSONResponse:
    """Drive to an end stop for the sole purpose of making the position certain."""
    tracker = _tracker(request)
    if shutter_id not in tracker.settings.shutters:
        raise HTTPException(
            404,
            detail={
                "error": "unknown_shutter",
                "message": f"Kein Rolladen {shutter_id!r}.",
                "detail": None,
            },
        )
    target = tracker.nearest_end_stop(shutter_id)
    bridge = request.app.state.bridge
    try:
        level = tracker.level_for(shutter_id, target)
        await bridge.send_level(tracker.settings.shutters[shutter_id].address, level)
        movement = await tracker.start_movement(shutter_id, target, level)
    except BridgeUnreachable:
        return JSONResponse({"accepted": False, **BRIDGE_UNREACHABLE}, status_code=503)
    return JSONResponse(
        {"accepted": True, "target_percent": target, "movement": movement_json(movement)}
    )


@router.get("/shutters/{shutter_id}")
async def get_shutter(request: Request, shutter_id: str) -> dict[str, Any]:
    tracker = _tracker(request)
    if shutter_id not in tracker.settings.shutters:
        raise HTTPException(
            404,
            detail={
                "error": "unknown_shutter",
                "message": f"Kein Rolladen {shutter_id!r}.",
                "detail": None,
            },
        )
    return shutter_json(shutter_id, tracker, getattr(request.app.state, "runs", None))


# --- simulator-only, registered only when bridge.kind == "sim" ----------------

sim_router = APIRouter(prefix="/api/sim")


class ReportBody(BaseModel):
    shutter_id: str
    percent: int = Field(ge=0, le=100)
    """The bridge's level, which is what a real report carries. Named percent
    because that is what it is called on the wire; the two coincide only when
    the travel curve is neutral."""


@sim_router.post("/bridge/{state}")
async def sim_bridge(request: Request, state: Literal["offline", "online"]) -> dict[str, Any]:
    bridge = request.app.state.bridge
    bridge.set_connected(state == "online")
    await request.app.state.bus.publish(
        {"type": "bridge", "connected": bridge.connected, "kind": bridge.kind}
    )
    return {"connected": bridge.connected}


@sim_router.get("/truth")
async def sim_truth(request: Request) -> dict[str, Any]:
    """What the simulated windows actually do.

    Only reachable with the simulator, and never through the bridge port the app
    talks to — calibration has to find these numbers by measuring, or it proves
    nothing.
    """
    tracker = _tracker(request)
    bridge = request.app.state.bridge
    out = {}
    for shutter_id, config in tracker.settings.shutters.items():
        sim = bridge._shutters.get(config.address)
        if sim is None:
            continue
        out[shutter_id] = {
            "dead_seconds": round(sim.dead_time, 2),
            "travel_up_seconds": round(sim.travel_up, 2),
            "travel_down_seconds": round(sim.travel_down, 2),
            "curve_a": sim.curve_a,
            "percent_now": round(sim.percent, 1),
            "command_to_arrival_up": round(sim.dead_time + sim.travel_up, 2),
            "command_to_arrival_down": round(sim.dead_time + sim.travel_down, 2),
        }
    return out


@sim_router.post("/report")
async def sim_report(request: Request, body: ReportBody) -> dict[str, Any]:
    tracker = _tracker(request)
    if body.shutter_id not in tracker.settings.shutters:
        raise HTTPException(
            404, detail={"error": "unknown_shutter", "message": "unbekannt", "detail": None}
        )
    address = tracker.settings.shutters[body.shutter_id].address
    # the same entry point the bridge's reports use, so a report injected here
    # disturbs a measurement exactly as a real one would
    await request.app.state.on_report(address, body.percent)
    return {
        "applied": True,
        "as_percent": tracker.percent_from_level(body.shutter_id, body.percent),
        "position": shutter_json(body.shutter_id, tracker)["position"],
    }
