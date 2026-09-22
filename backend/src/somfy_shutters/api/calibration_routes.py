"""The calibration endpoints.

Timestamps are taken here, on arrival of the request and on a monotonic clock,
rather than trusting anything a client sends. A measurement is the one number in
this system that nothing else can check.
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..bridge.base import BridgeUnreachable
from ..calibration import (
    ActiveRun,
    CalibrationError,
    at_curve_limit,
    midpoint_shift,
    nearest_end_stop,
    plan_run,
    rejection_for,
)
from ..models import (
    CheckReply,
    Direction,
    MeasurementRun,
    RunKind,
    utcnow,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calibration")

BRIDGE_UNREACHABLE = {
    "error": "bridge_unreachable",
    "message": "Der Befehl konnte nicht zugestellt werden. Die Funkbrücke antwortet nicht.",
    "detail": None,
}


def _parts(request: Request) -> tuple[Any, Any, Any, Any]:
    state = request.app.state
    return state.tracker, state.calibration, state.runs, state.bridge


def _require_shutter(tracker: Any, shutter_id: str) -> None:
    if shutter_id not in tracker.settings.shutters:
        raise HTTPException(
            404,
            detail={
                "error": "unknown_shutter",
                "message": f"Kein Rolladen {shutter_id!r}.",
                "detail": None,
            },
        )


async def _announce(
    request: Request, shutter_id: str, active: bool, direction: str | None = None
) -> None:
    """Tell every open client that a measurement started or ended."""
    await request.app.state.bus.publish(
        {
            "type": "measuring",
            "shutter_id": shutter_id,
            "active": active,
            "direction": direction,
        }
    )


def _conflict(exc: CalibrationError, extra: dict[str, Any] | None = None) -> JSONResponse:
    body = {"error": exc.code, "message": exc.message, "detail": None}
    body.update(extra or {})
    return JSONResponse(body, status_code=409)


def _direction_state(service: Any, shutter_id: str, direction: Direction) -> dict[str, Any]:
    value = service.effective(shutter_id, direction)
    return {
        "travel_seconds": value.travel_seconds,
        "dead_seconds": value.dead_seconds,
        "runs": value.runs,
        "curve_a": round(value.curve_a, 3),
        "source": value.source,
        "updated_at": value.updated_at.isoformat() if value.updated_at else None,
    }


def _state_word(up: dict[str, Any], down: dict[str, Any]) -> str:
    """One word for the list. A hand-written value outranks everything else.

    Not because it is the most precise state to report, but because it is the
    one that answers "why did my measurement not take effect". Which directions
    are measured is visible in the rows underneath.
    """
    sources = {up["source"], down["source"]}
    if "manual" in sources:
        return "manual"
    if sources == {"measured"}:
        return "calibrated"
    if "measured" in sources:
        return "partial"
    return "uncalibrated"


def _shutter_json(tracker: Any, service: Any, shutter_id: str) -> dict[str, Any]:
    config = tracker.settings.shutters[shutter_id]
    up = _direction_state(service, shutter_id, Direction.UP)
    down = _direction_state(service, shutter_id, Direction.DOWN)
    return {
        "id": config.id,
        "name": config.name,
        "state": _state_word(up, down),
        "up": up,
        "down": down,
    }


def _run_json(run: Any) -> dict[str, Any]:
    return {
        "id": run.id,
        "direction": run.direction.value,
        "dead_seconds": run.dead_seconds,
        "total_seconds": run.total_seconds,
        "recorded_at": run.recorded_at.isoformat(),
        "kind": run.kind.value,
        "rejected": run.rejected,
    }


# --- reading -----------------------------------------------------------------


@router.get("")
async def list_calibration(request: Request) -> dict[str, Any]:
    tracker, service, _, _ = _parts(request)
    return {"shutters": [_shutter_json(tracker, service, sid) for sid in tracker.settings.shutters]}


@router.get("/{shutter_id}")
async def get_calibration(request: Request, shutter_id: str) -> dict[str, Any]:
    tracker, service, runs, _ = _parts(request)
    _require_shutter(tracker, shutter_id)
    body = _shutter_json(tracker, service, shutter_id)
    body["runs"] = [_run_json(r) for r in service.runs_for(shutter_id)]
    active = runs.get(shutter_id)
    body["active_run"] = (
        None
        if active is None
        else {
            "direction": active.direction.value,
            "phase": active.phase,
            "elapsed_seconds": round(active.elapsed(time.monotonic()), 2),
        }
    )
    return body


# --- the guided run ----------------------------------------------------------


@router.post("/{shutter_id}/run")
async def start_run(request: Request, shutter_id: str) -> JSONResponse:
    tracker, service, runs, bridge = _parts(request)
    _require_shutter(tracker, shutter_id)
    current = tracker.position(shutter_id).percent

    try:
        established = {
            "up": service.established_total(shutter_id, Direction.UP) or 0.0,
            "down": service.established_total(shutter_id, Direction.DOWN) or 0.0,
        }
        plan = plan_run(current, established)
    except CalibrationError as exc:
        return _conflict(exc, {"suggested_target": nearest_end_stop(current)})

    target = 100 if plan.direction is Direction.UP else 0
    expected = plan.expected_total or tracker._travel_seconds(shutter_id, plan.direction)

    request.app.state.pending_checks.pop(shutter_id, None)
    try:
        runs.start(
            ActiveRun(
                shutter_id=shutter_id,
                direction=plan.direction,
                started_monotonic=time.monotonic(),
                expected_total=expected,
                kind=RunKind.GUIDED,
            )
        )
    except CalibrationError as exc:
        return _conflict(exc)

    try:
        await bridge.send_level(
            tracker.settings.shutters[shutter_id].address, tracker.level_for(shutter_id, target)
        )
        await tracker.start_movement(shutter_id, target)
    except BridgeUnreachable:
        runs.finish(shutter_id)
        # The run existed for a moment, and a client connecting in that moment
        # got a snapshot saying so. Nothing else would ever tell it otherwise.
        await _announce(request, shutter_id, False)
        return JSONResponse(BRIDGE_UNREACHABLE, status_code=503)

    log.info("calibration run started on %s, direction %s", shutter_id, plan.direction.value)
    await _announce(request, shutter_id, True, plan.direction.value)
    return JSONResponse(
        {
            "direction": plan.direction.value,
            "from_percent": plan.from_percent,
            "expected_total_seconds": round(expected, 2),
        }
    )


@router.post("/{shutter_id}/home")
async def home(request: Request, shutter_id: str) -> JSONResponse:
    """The drive to an end stop that is explicitly not a measurement (FR-003)."""
    tracker, _, runs, bridge = _parts(request)
    _require_shutter(tracker, shutter_id)
    if runs.is_measuring(shutter_id):
        return _conflict(CalibrationError("already_running", "Es läuft gerade eine Messung."))

    target = nearest_end_stop(tracker.position(shutter_id).percent)
    try:
        await bridge.send_level(
            tracker.settings.shutters[shutter_id].address, tracker.level_for(shutter_id, target)
        )
        movement = await tracker.start_movement(shutter_id, target)
    except BridgeUnreachable:
        return JSONResponse(BRIDGE_UNREACHABLE, status_code=503)
    return JSONResponse(
        {
            "accepted": True,
            "target_percent": target,
            "measured": False,
            "expected_arrival": movement.expected_arrival.isoformat() if movement else None,
        }
    )


class MarkBody(BaseModel):
    mark: Literal["moving", "arrived"]


@router.post("/{shutter_id}/mark")
async def mark(request: Request, shutter_id: str, body: MarkBody) -> JSONResponse:
    tracker, service, runs, _ = _parts(request)
    _require_shutter(tracker, shutter_id)
    active = runs.get(shutter_id)
    if active is None:
        return _conflict(CalibrationError("no_run", "Für diesen Rolladen läuft keine Messung."))

    now = time.monotonic()

    if body.mark == "moving":
        dead = active.mark_moving(now)
        return JSONResponse({"phase": active.phase, "dead_seconds": round(dead, 2)})

    finished = runs.finish(shutter_id)
    established = service.established_total(shutter_id, finished.direction)
    run = finished.finish(now, established, recorded_at=utcnow())
    stored = service.record(run, now=utcnow())

    # The user just observed the arrival, which beats our own timer — that timer
    # runs on the travel time this very run is measuring.
    arrived_at = 100 if finished.direction is Direction.UP else 0
    await tracker.confirm_arrival(shutter_id, arrived_at)

    if stored is not None:
        await request.app.state.bus.publish(
            {
                "type": "calibration",
                "shutter_id": shutter_id,
                "direction": finished.direction.value,
                "travel_seconds": stored.travel_seconds,
                "runs": stored.runs,
            }
        )

    await _announce(request, shutter_id, False)
    next_direction = Direction.DOWN if finished.direction is Direction.UP else Direction.UP
    return JSONResponse(
        {
            "run": _run_json(run),
            "calibration": _direction_state(service, shutter_id, finished.direction),
            "next_direction": next_direction.value,
        }
    )


@router.delete("/{shutter_id}/run")
async def abort_run(request: Request, shutter_id: str) -> JSONResponse:
    """Stop measuring. The shutter stays where it is, so its position stops being
    certain — feature 001's confidence handling takes it from there (FR-008)."""
    tracker, _, runs, bridge = _parts(request)
    _require_shutter(tracker, shutter_id)
    try:
        runs.finish(shutter_id)
    except CalibrationError as exc:
        return _conflict(exc)

    # The run is aborted either way; a bridge that cannot take the halt does not
    # change that.
    with contextlib.suppress(BridgeUnreachable):
        await bridge.send_level(
            tracker.settings.shutters[shutter_id].address, tracker.halt_level(shutter_id)
        )
    await tracker.stop(shutter_id)
    await _announce(request, shutter_id, False)
    return JSONResponse({"aborted": True})


@router.delete("/{shutter_id}")
async def clear(request: Request, shutter_id: str) -> dict[str, Any]:
    """FR-016. shutters.toml is not touched — the app does not write that file."""
    tracker, service, _, _ = _parts(request)
    _require_shutter(tracker, shutter_id)
    service.clear(shutter_id)
    return _shutter_json(tracker, service, shutter_id)


@router.post("/{shutter_id}/confirm")
async def confirm(request: Request, shutter_id: str) -> JSONResponse:
    """One tap: the shutter has arrived.

    The elapsed time from the command to this request is a real observation, and
    the only kind this system can get without a person holding a stopwatch. The
    travel itself measures nothing — its arrival was computed from the number we
    are trying to find out.
    """
    tracker, service, _, _ = _parts(request)
    _require_shutter(tracker, shutter_id)

    pending = request.app.state.pending_confirmations.pop(shutter_id, None)
    if pending is None:
        return _conflict(
            CalibrationError("nothing_to_confirm", "Für diesen Rolladen steht keine Frage offen.")
        )

    total = time.monotonic() - pending.started_monotonic
    established = service.established_total(shutter_id, pending.direction)
    run = MeasurementRun(
        shutter_id=shutter_id,
        direction=pending.direction,
        dead_seconds=service.effective(shutter_id, pending.direction).dead_seconds,
        total_seconds=round(total, 3),
        recorded_at=utcnow(),
        kind=RunKind.CONFIRMED,
        rejected=rejection_for(
            service.effective(shutter_id, pending.direction).dead_seconds, total, established
        ),
    )
    stored = service.record(run, now=utcnow())
    if stored is not None:
        await request.app.state.bus.publish(
            {
                "type": "calibration",
                "shutter_id": shutter_id,
                "direction": pending.direction.value,
                "travel_seconds": stored.travel_seconds,
                "runs": stored.runs,
            }
        )
    return JSONResponse(
        {
            "run": _run_json(run),
            "calibration": _direction_state(service, shutter_id, pending.direction),
        }
    )


@router.delete("/{shutter_id}/confirm")
async def dismiss(request: Request, shutter_id: str) -> dict[str, Any]:
    """Ignored, or answered "not yet". Nothing is recorded and nothing inferred
    from the silence (FR-018a)."""
    request.app.state.pending_confirmations.pop(shutter_id, None)
    return {"dismissed": True}


# --- verification ------------------------------------------------------------


@router.post("/{shutter_id}/check")
async def start_check(request: Request, shutter_id: str) -> JSONResponse:
    tracker, service, runs, bridge = _parts(request)
    _require_shutter(tracker, shutter_id)
    if runs.is_measuring(shutter_id):
        return _conflict(CalibrationError("already_running", "Es läuft gerade eine Messung."))
    if service.effective(shutter_id, Direction.UP).source == "default":
        return _conflict(
            CalibrationError(
                "not_calibrated", "Erst messen, dann prüfen — es gibt noch nichts zu prüfen."
            )
        )

    try:
        await bridge.send_level(
            tracker.settings.shutters[shutter_id].address, tracker.level_for(shutter_id, 50)
        )
        movement = await tracker.start_movement(shutter_id, 50)
    except BridgeUnreachable:
        return JSONResponse(BRIDGE_UNREACHABLE, status_code=503)
    # The curve is per direction, so the answer has to land on the one this
    # drive used. Already standing at 50 %, the way it got there decides.
    direction = (
        movement.direction
        if movement is not None
        else tracker.last_direction(shutter_id) or Direction.UP
    )
    request.app.state.pending_checks[shutter_id] = direction
    return JSONResponse(
        {
            "accepted": True,
            "target_percent": 50,
            "direction": direction.value,
            "expected_arrival": movement.expected_arrival.isoformat() if movement else None,
        }
    )


class AnswerBody(BaseModel):
    answer: Literal["too_high", "about_right", "too_low"]


@router.post("/{shutter_id}/check/answer")
async def answer_check(request: Request, shutter_id: str, body: AnswerBody) -> Any:
    """One answer per drive to the midpoint.

    An answer describes what the person sees at the check position. Without a
    drive there is no such position, and after one answer the curve has moved,
    so the shutter no longer stands at the new midpoint — accepting a second
    answer there shifts the curve again for something nobody looked at.
    """
    tracker, service, runs, _ = _parts(request)
    _require_shutter(tracker, shutter_id)
    if runs.is_measuring(shutter_id):
        return _conflict(CalibrationError("already_running", "Es läuft gerade eine Messung."))
    direction = request.app.state.pending_checks.pop(shutter_id, None)
    if direction is None:
        return _conflict(
            CalibrationError("no_check", "Erst auf die Mitte fahren, dann sagen, wie es aussieht.")
        )
    value = service.answer_check(shutter_id, direction, CheckReply(body.answer))
    return {
        "direction": direction.value,
        "curve_a": round(value.curve_a, 3),
        "shift_pp": round(abs(midpoint_shift(value.curve_a)), 1),
        "at_limit": at_curve_limit(value.curve_a),
    }


@router.delete("/{shutter_id}/check")
async def clear_check(request: Request, shutter_id: str) -> dict[str, Any]:
    """FR-026: undo the verification, keep the measurements."""
    tracker, service, _, _ = _parts(request)
    _require_shutter(tracker, shutter_id)
    service.clear_checks(shutter_id)
    request.app.state.pending_checks.pop(shutter_id, None)
    return _shutter_json(tracker, service, shutter_id)
