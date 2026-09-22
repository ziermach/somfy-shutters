"""Credentials and pairing over REST (specs/008-api-auth-audit/contracts/rest.md).

`POST /api/auth/pair` is the one route that needs no credential: it is how a
device gets one. Everything else here needs `manage`, except asking who one is.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..auth.gate import COOKIE, WATCH, caller_of
from ..auth.models import MAX_NAME, Actor, Credential, ordered
from ..auth.tokens import normalise_code

router = APIRouter(prefix="/api/auth")

COOKIE_MAX_AGE = 315_360_000  # ten years; the credential's own expiry is what counts


def error(status: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    return JSONResponse({"error": code, "message": message, "detail": detail}, status_code=status)


def local(request: Request, at: datetime | None) -> str | None:
    return at.astimezone(request.app.state.settings.general.tz).isoformat() if at else None


def credential_json(request: Request, credential: Credential) -> dict[str, Any]:
    now = request.app.state.auth.clock()
    return {
        "id": credential.id,
        "name": credential.name,
        "abilities": ordered(credential.abilities),
        "origin": credential.origin,
        "created_at": local(request, credential.created_at),
        "last_used_at": local(request, credential.last_used_at),
        "expires_at": local(request, credential.expires_at),
        "revoked_at": local(request, credential.revoked_at),
        "state": credential.state(now),
        "is_me": caller_of(request).credential_id == credential.id,
    }


def secure(request: Request) -> bool:
    """HTTPS seen directly, or reported by the one proxy we trust."""
    if request.url.scheme == "https":
        return True
    gate = request.app.state.gate
    peer = request.client.host if request.client else None
    return bool(
        gate.trusted_proxy
        and peer == gate.trusted_proxy
        and request.headers.get("x-forwarded-proto") == "https"
    )


@router.get("/me", dependencies=WATCH)
async def me(request: Request) -> dict[str, Any]:
    caller = caller_of(request)
    mode = "required" if request.app.state.gate.required else "open"
    if caller.credential_id is None:
        return {
            "id": None,
            "name": caller.actor.name,
            "abilities": ordered(caller.abilities),
            "origin": caller.actor.kind,
            "expires_at": None,
            "mode": mode,
        }
    credential = request.app.state.auth.get(caller.credential_id)
    return {**credential_json(request, credential), "mode": mode}


class PairBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str = Field(min_length=1)
    token: bool = False
    """True for a client that is not a browser: the token comes back in the body."""

    @field_validator("name")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > MAX_NAME:
            raise ValueError(f"name must be 1 to {MAX_NAME} characters")
        return value


@router.post("/pair", status_code=201)
async def pair(request: Request) -> Any:
    """Exchange a pairing code for this device's own credential (FR-030, FR-031)."""
    gate = request.app.state.gate
    audit = request.app.state.audit
    locked = gate.locked_out(request)
    if locked is not None:
        raise locked
    try:
        body = PairBody.model_validate(await request.json())
    except (ValidationError, ValueError):
        return error(422, "invalid_pairing", "Bitte Code und Gerätenamen angeben.")
    if normalise_code(body.code) is None:
        return error(422, "invalid_pairing", "Ein Kopplungscode hat sechs Zeichen.")

    result = request.app.state.auth.redeem(body.code, body.name)
    if isinstance(result, str):
        audit.record(
            Actor("anonymous", name=body.name),
            "pairing_failed",
            "refused_auth",
            detail={"reason": result, "source": gate.source(request)},
            clock_ok=gate.clock_ok(),
        )
        guesses = getattr(request.app.state, "guesses", None)
        if guesses is not None:
            guesses.wrong()
        # One refusal for every kind of bad code, counted like a failed login
        # (FR-033) — and recorded once, as pairing_failed above.
        raise gate.refuse_auth(request, "pairing", record=False)

    record, credential, token = result
    audit.record(
        Actor("credential", credential.id, credential.name),
        "pairing_redeemed",
        "accepted",
        target=record.id,
        detail={"abilities": ordered(credential.abilities), "origin": credential.origin},
        clock_ok=gate.clock_ok(),
    )
    payload: dict[str, Any] = {"credential": credential_json(request, credential)}
    if body.token:
        payload["token"] = token
        return JSONResponse(payload, status_code=201)
    response = JSONResponse(payload, status_code=201)
    response.set_cookie(
        COOKIE,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=secure(request),
        path="/",
    )
    return response
