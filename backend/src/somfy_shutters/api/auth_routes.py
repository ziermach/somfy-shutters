"""Credentials and pairing over REST (specs/008-api-auth-audit/contracts/rest.md).

`POST /api/auth/pair` is the one route that needs no credential: it is how a
device gets one. Everything else here needs `manage`, except asking who one is.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..auth.gate import COOKIE, MANAGE, WATCH, caller_of
from ..auth.models import (
    MAX_NAME,
    SYSTEM,
    Ability,
    Actor,
    Credential,
    CredentialDraft,
    PairingCode,
    ordered,
    with_watch,
)
from ..auth.tokens import format_code, normalise_code

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


# --- credentials (manage) -------------------------------------------------------------


def exceeds_own(request: Request, wanted: frozenset[Ability]) -> JSONResponse | None:
    """FR-011, FR-032: nobody hands on more than they hold."""
    extra = wanted - caller_of(request).abilities
    if not extra:
        return None
    return error(
        403,
        "exceeds_own",
        "Mehr Rechte, als dieses Gerät selbst hat.",
        {"abilities": ordered(frozenset(extra))},
    )


def invalid(exc: ValidationError, code: str, message: str) -> JSONResponse:
    first = exc.errors()[0]
    where = ".".join(str(p) for p in first["loc"])
    return error(422, code, message, {"field": where, "problem": first["msg"]})


@router.get("/credentials", dependencies=MANAGE)
async def list_credentials(request: Request) -> dict[str, Any]:
    return {"credentials": [credential_json(request, c) for c in request.app.state.auth.list()]}


@router.post("/credentials", status_code=201, dependencies=MANAGE)
async def issue_credential(request: Request) -> Any:
    try:
        draft = CredentialDraft.model_validate(await request.json())
    except ValidationError as exc:
        return invalid(exc, "invalid_credential", "Der Zugang ist so nicht gültig.")
    wanted = with_watch(frozenset(draft.abilities))
    refused = exceeds_own(request, wanted)
    if refused is not None:
        return refused
    caller = caller_of(request)
    credential, token = request.app.state.auth.issue(
        draft.name,
        wanted,
        origin="issued",
        created_by=caller.credential_id,
        expires_at=draft.expires_at,
    )
    request.app.state.audit.record(
        caller.actor,
        "credential_issued",
        "accepted",
        target=credential.id,
        detail={"name": credential.name, "abilities": ordered(credential.abilities)},
        clock_ok=request.app.state.gate.clock_ok(),
    )
    return JSONResponse({**credential_json(request, credential), "token": token}, status_code=201)


@router.delete("/credentials/{credential_id}", dependencies=MANAGE)
async def revoke_credential(request: Request, credential_id: str) -> Any:
    auth = request.app.state.auth
    credential = auth.get(credential_id)
    if credential is None:
        return error(404, "unknown_credential", "Diesen Zugang gibt es nicht.")
    try:
        raw = await request.json()
    except ValueError:
        raw = {}
    confirmed = isinstance(raw, dict) and raw.get("confirm_lockout") is True
    if not confirmed and auth.permanent_managers(excluding=credential_id) == 0:
        # FR-013: afterwards no device could manage devices for good. Say so first.
        return error(
            409,
            "last_manager",
            "Danach könnte kein Gerät mehr Geräte verwalten. Zurück kommt man dann nur "
            "noch mit »somfy-shutters auth recover« auf dem Pi.",
        )
    caller = caller_of(request)
    if auth.revoke(credential_id, by=caller.credential_id):
        cancelled = auth.cancel_minted_by(credential_id)
        request.app.state.audit.record(
            caller.actor,
            "credential_revoked",
            "accepted",
            target=credential_id,
            detail={"name": credential.name, "codes_cancelled": len(cancelled)},
            clock_ok=request.app.state.gate.clock_ok(),
        )
        # FR-005: its open live feeds end now, not when the phone next reconnects.
        await request.app.state.hub.close_for(credential_id)
    return Response(status_code=204)


# --- pairing codes (manage) -------------------------------------------------------------


class MintBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    abilities: list[Ability] = Field(min_length=1)


def code_json(request: Request, code: PairingCode) -> dict[str, Any]:
    return {
        "id": code.id,
        "abilities": ordered(code.abilities),
        "expires_at": local(request, code.expires_at),
    }


@router.get("/pairing", dependencies=MANAGE)
async def outstanding_codes(request: Request) -> dict[str, Any]:
    """Outstanding codes — never the code itself, which is not stored."""
    return {"codes": [code_json(request, c) for c in request.app.state.auth.outstanding()]}


@router.post("/pairing", status_code=201, dependencies=MANAGE)
async def mint_code(request: Request) -> Any:
    try:
        body = MintBody.model_validate(await request.json())
    except ValidationError as exc:
        return invalid(exc, "invalid_pairing", "Diese Rechte gibt es nicht.")
    wanted = with_watch(frozenset(body.abilities))
    refused = exceeds_own(request, wanted)
    if refused is not None:
        return refused
    caller = caller_of(request)
    minutes = request.app.state.settings.auth.pairing_minutes
    record, code = request.app.state.auth.mint(wanted, caller.credential_id, minutes)
    request.app.state.guesses.minted()
    request.app.state.audit.record(
        caller.actor,
        "pairing_minted",
        "accepted",
        target=record.id,
        detail={"abilities": ordered(record.abilities)},
        clock_ok=request.app.state.gate.clock_ok(),
    )
    return JSONResponse({**code_json(request, record), "code": format_code(code)}, status_code=201)


@router.delete("/pairing/{code_id}", dependencies=MANAGE)
async def cancel_code(request: Request, code_id: str) -> Any:
    if not request.app.state.auth.cancel(code_id):
        return error(404, "unknown_code", "Diesen Kopplungscode gibt es nicht (mehr).")
    caller = caller_of(request)
    request.app.state.audit.record(
        caller.actor,
        "pairing_cancelled",
        "accepted",
        target=code_id,
        detail={"by": "owner"},
        clock_ok=request.app.state.gate.clock_ok(),
    )
    return Response(status_code=204)


class Guesses:
    """Research §7: ten wrong codes in total while any code is outstanding cancel them all.

    Per-address lockout alone would give a guesser with many addresses ten tries
    each; this caps the whole house at ten against the codes that exist right now.
    """

    LIMIT = 10

    def __init__(self, auth: Any, audit: Any) -> None:
        self.auth = auth
        self.audit = audit
        self.count = 0

    def minted(self) -> None:
        if len(self.auth.outstanding()) <= 1:
            self.count = 0  # nothing was outstanding before this one

    def wrong(self) -> None:
        if not self.auth.outstanding():
            self.count = 0
            return
        self.count += 1
        if self.count < self.LIMIT:
            return
        for code_id in self.auth.cancel_outstanding():
            self.audit.record(
                SYSTEM, "pairing_cancelled", "accepted", target=code_id, detail={"by": "guessing"}
            )
        self.count = 0
