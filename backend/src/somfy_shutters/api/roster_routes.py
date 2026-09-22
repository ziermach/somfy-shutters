"""Adding and removing shutters (feature 005, contracts/rest.md).

The app never creates, programs or deletes a shutter in the bridge. It reads what the
bridge announces and lets a person confirm, rename, set aside and restore.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth.gate import CONFIGURE, WATCH
from ..roster import ConfiguredByHand, MeasurementInProgress, NameTaken, NotAnnounced, Roster
from .serialize import shutter_json

router = APIRouter(prefix="/api")


class NameBody(BaseModel):
    name: str


def error(status: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    return JSONResponse({"error": code, "message": message, "detail": detail}, status_code=status)


NAME_TAKEN = (409, "name_taken", "Diesen Namen gibt es schon.")
INVALID_NAME = (422, "invalid_name", "Der Name muss 1 bis 40 Zeichen lang sein.")


def _roster(request: Request) -> Roster:
    return request.app.state.roster


@router.get("/roster", dependencies=WATCH)
async def get_roster(request: Request) -> dict[str, Any]:
    return _roster(request).wire()


@router.post("/roster/new/{address}", dependencies=CONFIGURE)
async def confirm_new(request: Request, address: str, body: NameBody) -> JSONResponse:
    try:
        shutter = await _roster(request).confirm(address, body.name)
    except NotAnnounced:
        return error(
            404,
            "not_announced",
            "Die Funkbrücke meldet unter dieser Adresse keinen neuen Rolladen.",
        )
    except NameTaken:
        return error(*NAME_TAKEN)
    except ValueError:
        return error(*INVALID_NAME)
    state = request.app.state
    return JSONResponse(
        shutter_json(shutter.id, state.tracker, getattr(state, "runs", None)), status_code=201
    )


UNKNOWN = (404, "unknown_shutter", "Diesen Rolladen gibt es nicht.")
REFUSED = {
    "configured_by_hand": (
        409,
        "configured_by_hand",
        "Dieser Rolladen ist in config/shutters.toml eingetragen. Entfernt wird er dort.",
    ),
    "measurement_in_progress": (
        409,
        "measurement_in_progress",
        "Für diesen Rolladen läuft gerade eine Messung. Erst beenden oder abbrechen.",
    ),
}


@router.get("/shutters/{shutter_id}/removal", dependencies=WATCH)
async def removal_preview(request: Request, shutter_id: str) -> JSONResponse:
    try:
        return JSONResponse(_roster(request).removal_preview(shutter_id))
    except KeyError:
        return error(*UNKNOWN)


@router.delete("/shutters/{shutter_id}", dependencies=CONFIGURE)
async def remove(request: Request, shutter_id: str) -> JSONResponse:
    """Sends nothing to the bridge (FR-015)."""
    try:
        set_aside = await _roster(request).remove(shutter_id)
    except KeyError:
        return error(*UNKNOWN)
    except ConfiguredByHand:
        return error(*REFUSED["configured_by_hand"])
    except MeasurementInProgress:
        return error(*REFUSED["measurement_in_progress"])
    return JSONResponse({"removed": shutter_id, "set_aside": set_aside})


@router.post("/roster/set-aside/{address}/restore", dependencies=CONFIGURE)
async def restore(request: Request, address: str) -> JSONResponse:
    try:
        await _roster(request).restore(address.strip().lower())
    except KeyError:
        return error(404, "unknown_address", "Unter dieser Adresse liegt nichts beiseite.")
    return JSONResponse(_roster(request).wire())
