"""Adding and removing shutters (feature 005, contracts/rest.md).

The app never creates, programs or deletes a shutter in the bridge. It reads what the
bridge announces and lets a person confirm, rename, set aside and restore.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..roster import NameTaken, NotAnnounced, Roster
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


@router.get("/roster")
async def get_roster(request: Request) -> dict[str, Any]:
    return _roster(request).wire()


@router.post("/roster/new/{address}")
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
