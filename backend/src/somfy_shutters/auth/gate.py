"""The door (specs/008-api-auth-audit/research.md §2, §4, §5).

Every `/api/*` route declares the ability it needs with `require(...)`; a test walks
the routes and fails for any that does not, so a route added later cannot be left
open by forgetting. A caller is resolved from a bearer header, else from the `sst`
cookie the web app got by pairing. Every authentication failure looks the same to
the caller; the record, not the response, says which kind it was.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, Request
from starlette.requests import HTTPConnection

from .audit import AuditLog
from .models import ANONYMOUS, SIMULATOR, Ability, Actor, Caller
from .store import AuthStore

COOKIE = "sst"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

UNAUTHORIZED = {
    "error": "unauthorized",
    "message": "Dieses Gerät ist nicht angemeldet.",
    "detail": None,
}
THROTTLED_MESSAGE = "Zu viele Versuche. Bitte kurz warten."


class Refused(Exception):
    """Turned into a response by the handler main.py installs."""

    def __init__(self, status: int, body: dict[str, Any], headers: dict[str, str] | None = None):
        super().__init__(body["error"])
        self.status = status
        self.body = body
        self.headers = headers or {}


def forbidden(needs: Ability) -> Refused:
    body = {"error": "forbidden", "message": "Dieses Gerät darf das nicht."}
    return Refused(403, {**body, "detail": {"needs": needs.value}})


class Gate:
    def __init__(
        self,
        required: bool,
        store: AuthStore,
        audit: AuditLog,
        throttle: Any = None,
        trusted_proxy: str | None = None,
        clock_ok: Callable[[], bool] = lambda: True,
    ) -> None:
        self.required = required
        self.store = store
        self.audit = audit
        self.throttle = throttle
        self.trusted_proxy = trusted_proxy
        self.clock_ok = clock_ok

    # --- who is asking ---------------------------------------------------------

    def source(self, conn: HTTPConnection) -> str:
        """The socket peer; X-Forwarded-For only from the configured proxy (research §8)."""
        peer = conn.client.host if conn.client else "unknown"
        if self.trusted_proxy and peer == self.trusted_proxy:
            forwarded = conn.headers.get("x-forwarded-for", "")
            first = forwarded.split(",")[0].strip()
            if first:
                return first
        return peer

    @staticmethod
    def presented(conn: HTTPConnection) -> tuple[str | None, str | None]:
        """(token, via). A bearer header wins over the cookie."""
        header = conn.headers.get("authorization", "")
        if header[:7].lower() == "bearer ":
            return header[7:].strip(), "bearer"
        cookie = conn.cookies.get(COOKIE)
        if cookie:
            return cookie, "cookie"
        return None, None

    @staticmethod
    def same_origin(conn: HTTPConnection) -> bool:
        origin = conn.headers.get("origin")
        if origin is None:
            return False
        scheme = "https" if conn.url.scheme in ("https", "wss") else "http"
        return origin == f"{scheme}://{conn.url.netloc}"

    def refuse_auth(
        self, conn: HTTPConnection, reason: str, *, count: bool = True, record: bool = True
    ) -> Refused:
        source = self.source(conn)
        # Presenting nothing is not a guess: an unpaired phone opening the app asks
        # twice per load, and counting that would lock it out of pairing itself.
        if count and reason != "none" and self.throttle is not None:
            self.throttle.fail(source)
        if count and record:
            self.audit.record(
                ANONYMOUS,
                "auth_failed",
                "refused_auth",
                detail={"reason": reason, "source": source, "path": conn.url.path},
                clock_ok=self.clock_ok(),
            )
        return Refused(401, dict(UNAUTHORIZED))

    def locked_out(self, conn: HTTPConnection) -> Refused | None:
        if self.throttle is None:
            return None
        wait = self.throttle.locked(self.source(conn))
        if wait is None:
            return None
        return Refused(
            429,
            {"error": "throttled", "message": THROTTLED_MESSAGE, "detail": None},
            {"Retry-After": str(int(wait) + 1)},
        )

    def caller(self, conn: HTTPConnection, *, unsafe: bool, count: bool = True) -> Caller:
        """Resolve or raise Refused. In open mode everyone is the simulator."""
        if not self.required:
            return SIMULATOR
        locked = self.locked_out(conn)
        if locked is not None:
            raise locked
        token, via = self.presented(conn)
        if token is None:
            raise self.refuse_auth(conn, "none", count=count)
        found = self.store.resolve(token)
        if isinstance(found, str):
            raise self.refuse_auth(conn, found, count=count)
        if via == "cookie" and unsafe and not self.same_origin(conn):
            # A cookie travels by itself; an Origin from elsewhere means somebody
            # else's page is spending it (research §2).
            raise Refused(
                403,
                {"error": "bad_origin", "message": "Anfrage von fremder Seite.", "detail": None},
            )
        self.store.touch(found.id)
        return Caller(Actor("credential", found.id, found.name), found.abilities, found.id, via)

    def optional(self, conn: HTTPConnection) -> Caller | None:
        """For the health check: never recorded, never counted (research §4)."""
        try:
            return self.caller(conn, unsafe=False, count=False)
        except Refused:
            return None

    # --- what they may do ------------------------------------------------------

    def check(self, request: Request, ability: Ability) -> Caller:
        caller = self.caller(request, unsafe=request.method not in SAFE_METHODS)
        shutter_id = request.path_params.get("shutter_id")
        if not caller.can(ability):
            self.audit.record(
                caller.actor,
                "refused",
                "refused_permission",
                shutter_id=shutter_id,
                detail={"needs": ability.value, "path": request.url.path},
                clock_ok=self.clock_ok(),
            )
            raise forbidden(ability)
        if ability is Ability.COMMAND and self.throttle is not None and caller.credential_id:
            wait = self.throttle.take(caller.credential_id)
            if wait is not None:
                self.audit.record(
                    caller.actor,
                    "throttled",
                    "refused_throttle",
                    shutter_id=shutter_id,
                    detail={"kind": "command", "path": request.url.path},
                    clock_ok=self.clock_ok(),
                )
                raise Refused(
                    429,
                    {"error": "throttled", "message": THROTTLED_MESSAGE, "detail": None},
                    {"Retry-After": str(int(wait) + 1)},
                )
        request.state.caller = caller
        request.state.ability = ability
        request.state.shutter_id = shutter_id
        return caller


def require(ability: Ability) -> Callable[[Request], Caller]:
    """A route dependency. The attribute lets the every-route test see what it guards."""

    def guard(request: Request) -> Caller:
        return request.app.state.gate.check(request, ability)

    guard.ability = ability  # type: ignore[attr-defined]
    return guard


CHANGES = (
    ("/api/automations/pause", "pause_changed"),
    ("/api/automations", "rule_changed"),
    ("/api/location", "location_changed"),
    ("/api/groups", "group_changed"),
    ("/api/calibration", "calibration"),
    ("/api/roster", "shutter_added"),  # feature 005: taking one over, or back
    ("/api/shutters", "shutter_changed"),  # feature 005: renamed or removed
)
"""Which record entry a successful configuring or calibrating request becomes."""


def change_of(request: Request, status: int) -> str | None:
    """The record action for a request that changed configuration or measurements.

    Written once, after the response, and only when it succeeded — so the record
    says what was changed, not what was attempted (research §9, data-model.md).
    """
    ability = getattr(request.state, "ability", None)
    if ability not in (Ability.CONFIGURE, Ability.CALIBRATE) or status >= 400:
        return None
    if request.method in SAFE_METHODS or request.url.path == "/api/automations/preview":
        return None
    path = request.url.path
    return next((action for prefix, action in CHANGES if path.startswith(prefix)), None)


def caller_of(request: Request) -> Caller:
    """The caller a guarded route was entered by."""
    return getattr(request.state, "caller", SIMULATOR)


# For route decorators: `@router.get("/x", dependencies=WATCH)`.
WATCH = [Depends(require(Ability.WATCH))]
COMMAND = [Depends(require(Ability.COMMAND))]
CONFIGURE = [Depends(require(Ability.CONFIGURE))]
CALIBRATE = [Depends(require(Ability.CALIBRATE))]
MANAGE = [Depends(require(Ability.MANAGE))]
