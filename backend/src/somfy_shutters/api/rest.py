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

from .. import commands
from ..bridge.base import BridgeUnreachable, Report
from ..commands import MeasurementInProgress, ShutterForgotten
from ..roster import ConfiguredByHand, NameTaken
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


async def _apply(request: Request, shutter_id: str, body: CommandBody) -> dict[str, Any]:
    """Issue one command through the shared path (commands.apply)."""
    return await commands.apply(request.app.state, shutter_id, body.action, body.target_percent)


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


CONFIGURED_BY_HAND = {
    "error": "configured_by_hand",
    "message": "Dieser Rolladen ist in config/shutters.toml eingetragen und wird dort geändert.",
    "detail": None,
}

TARGET_REQUIRED = {
    "error": "target_required",
    "message": "Für 'position' fehlt target_percent.",
    "detail": None,
}


def many_status(results: list[dict[str, Any]]) -> int:
    """200 when every shutter took the command, 503 when none did, 207 in between."""
    accepted = sum(1 for r in results if r["accepted"])
    return 200 if accepted == len(results) else 503 if accepted == 0 else 207


@router.post("/shutters/command")
async def command_all(request: Request, body: CommandBody) -> JSONResponse:
    if body.action == "position" and body.target_percent is None:
        raise HTTPException(422, detail=TARGET_REQUIRED)
    # The others still move when one cannot; that one is reported with its reason.
    results = await commands.apply_many(
        request.app.state,
        list(_tracker(request).settings.shutters),
        body.action,
        body.target_percent,
    )
    return JSONResponse({"results": results}, status_code=many_status(results))


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
        raise HTTPException(422, detail=TARGET_REQUIRED)
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
    except ShutterForgotten:
        return JSONResponse(
            {
                "accepted": False,
                "error": "forgotten",
                "message": "Die Funkbrücke kennt diesen Rolladen nicht mehr.",
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


class RenameBody(BaseModel):
    name: str


@router.patch("/shutters/{shutter_id}")
async def rename_shutter(request: Request, shutter_id: str, body: RenameBody) -> JSONResponse:
    """Feature 005. The id never changes; groups, rules and history key on it."""
    try:
        await request.app.state.roster.rename(shutter_id, body.name)
    except KeyError:
        raise HTTPException(
            404,
            detail={
                "error": "unknown_shutter",
                "message": f"Kein Rolladen {shutter_id!r}.",
                "detail": None,
            },
        ) from None
    except ConfiguredByHand:
        return JSONResponse(CONFIGURED_BY_HAND, status_code=409)
    except NameTaken:
        return JSONResponse(
            {"error": "name_taken", "message": "Diesen Namen gibt es schon.", "detail": None},
            status_code=409,
        )
    except ValueError:
        return JSONResponse(
            {
                "error": "invalid_name",
                "message": "Der Name muss 1 bis 40 Zeichen lang sein.",
                "detail": None,
            },
            status_code=422,
        )
    return JSONResponse(
        shutter_json(shutter_id, _tracker(request), getattr(request.app.state, "runs", None))
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


class BridgeShutterBody(BaseModel):
    name: str = Field(min_length=1, max_length=40)


@sim_router.post("/bridge/shutters", status_code=201)
async def sim_bridge_add(request: Request, body: BridgeShutterBody) -> dict[str, Any]:
    """A person adds a shutter in the bridge's interface (feature 005). The bridge
    announces it — and accepts commands for it — only after a restart."""
    address = request.app.state.bridge.bridge_add(body.name.strip())
    return {"address": address, "name": body.name.strip(), "announced": False}


@sim_router.get("/bridge/shutters")
async def sim_bridge_list(request: Request) -> dict[str, Any]:
    return {"shutters": request.app.state.bridge.bridge_shutters()}


@sim_router.delete("/bridge/shutters/{address}", status_code=204)
async def sim_bridge_delete(request: Request, address: str) -> None:
    """A person deletes a shutter in the bridge. Its retained announcement stays."""
    if not request.app.state.bridge.bridge_delete(address.strip().lower()):
        raise HTTPException(
            404, detail={"error": "unknown_address", "message": "unbekannt", "detail": None}
        )


@sim_router.post("/bridge/restart")
async def sim_bridge_restart(request: Request) -> dict[str, Any]:
    """The bridge restarts: offline, online, every current shutter announced live."""
    bridge = request.app.state.bridge
    bridge.bridge_restart()
    await request.app.state.bus.publish(
        {"type": "bridge", "connected": bridge.connected, "kind": bridge.kind}
    )
    return {"connected": bridge.connected}


@sim_router.post("/bridge/{state}")
async def sim_bridge(request: Request, state: Literal["offline", "online"]) -> dict[str, Any]:
    bridge = request.app.state.bridge
    bridge.set_connected(state == "online")
    await request.app.state.bus.publish(
        {"type": "bridge", "connected": bridge.connected, "kind": bridge.kind}
    )
    return {"connected": bridge.connected}


class MovementBody(BaseModel):
    shutter_id: str
    state: Literal["opening", "closing", "open", "closed", "stopped"]


@sim_router.post("/movement")
async def sim_movement(request: Request, body: MovementBody) -> dict[str, Any]:
    """Inject a live movement report, as if the bridge heard a physical remote (feature 006)."""
    tracker = _tracker(request)
    if body.shutter_id not in tracker.settings.shutters:
        raise HTTPException(
            404, detail={"error": "unknown_shutter", "message": "unbekannt", "detail": None}
        )
    address = tracker.settings.shutters[body.shutter_id].address
    tracker.forget_bridge_run(body.shutter_id)
    await request.app.state.on_report(Report(address, kind="movement", state=body.state))
    return {"applied": True, "position": shutter_json(body.shutter_id, tracker)["position"]}


class LossBody(BaseModel):
    rate: float = Field(ge=0, le=1)


@sim_router.post("/loss")
async def sim_loss(request: Request, body: LossBody) -> dict[str, Any]:
    """Drop this share of commands in the air, silently (quickstart S3.3).

    One-way radio cannot tell a lost command from a delivered one; this is how to
    watch the app not pretend otherwise.
    """
    request.app.state.bridge.loss_rate = body.rate
    return {"loss_rate": body.rate}


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
    tracker.forget_bridge_run(body.shutter_id)
    await request.app.state.on_report(Report(address, body.percent))
    return {
        "applied": True,
        "as_percent": tracker.percent_from_level(body.shutter_id, body.percent),
        "position": shutter_json(body.shutter_id, tracker)["position"],
    }


@sim_router.post("/clock")
async def sim_clock(request: Request) -> dict[str, Any]:
    """Force the clock guard's verdict (feature 003, FR-013), or hand it back with null.

    Pulling the network cable on a development machine does not make its clock
    unreliable; this does, so the held path can be walked on purpose.
    """
    body = await request.json()
    reliable = body.get("reliable") if isinstance(body, dict) else None
    engine = request.app.state.automation
    engine.guard.override = None if reliable is None else bool(reliable)
    await engine.check_clock()
    return engine.state_json()
