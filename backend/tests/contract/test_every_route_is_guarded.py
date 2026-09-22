"""T011: no route under /api/ is open by accident (FR-002, research §4).

A route added later without `require(...)` fails here — that is the point. The
WebSocket authenticates inside its endpoint and is tested in test_ws_auth.py.
"""

from __future__ import annotations

import re

from fastapi.routing import APIRoute, APIWebSocketRoute

from .locked import issue, locked  # noqa: F401 — fixture

EXEMPT = {("GET", "/api/health"), ("POST", "/api/auth/pair")}
IN_ENDPOINT = {"/api/ws"}
UNAUTHORIZED = {
    "error": "unauthorized",
    "message": "Dieses Gerät ist nicht angemeldet.",
    "detail": None,
}
PARAMS = {
    "shutter_id": "wohnzimmer",
    "group_id": "g_x",
    "rule_id": "r_x",
    "state": "online",
    "credential_id": "c_x",
    "code_id": "p_x",
}


def abilities_of(route: APIRoute) -> list:
    return [
        d.call.ability  # type: ignore[attr-defined]
        for d in route.dependant.dependencies
        if hasattr(d.call, "ability")
    ]


def flat(routes) -> list:
    """Every route, also those inside included routers (FastAPI >= 0.140 wraps them)."""
    out = []
    for route in routes:
        inner = getattr(route, "original_router", None)
        out.extend(flat(inner.routes) if inner is not None else [route])
    return out


def api_routes(app) -> list[tuple[str, str, APIRoute]]:
    out = []
    for route in flat(app.routes):
        if isinstance(route, APIRoute) and route.path.startswith("/api/"):
            for method in route.methods:
                out.append((method, route.path, route))
    return out


async def test_the_route_list_is_not_empty(locked) -> None:  # noqa: F811
    """Without this, a change in how FastAPI nests routers would pass every test here."""
    assert len(api_routes(locked.app)) > 35


async def test_every_api_route_declares_an_ability(locked) -> None:  # noqa: F811
    open_routes = [
        (method, path)
        for method, path, route in api_routes(locked.app)
        if (method, path) not in EXEMPT and not abilities_of(route)
    ]
    assert open_routes == []


async def test_the_only_websocket_is_checked_in_its_endpoint(locked) -> None:  # noqa: F811
    sockets = {r.path for r in flat(locked.app.routes) if isinstance(r, APIWebSocketRoute)}
    assert sockets == IN_ENDPOINT


async def test_every_guarded_route_refuses_an_anonymous_caller(locked) -> None:  # noqa: F811
    before = (await locked.get("/api/sim/truth", headers=owner(locked))).json()
    checked = 0
    for method, path, _route in api_routes(locked.app):
        if (method, path) in EXEMPT:
            continue
        url = re.sub(r"\{(\w+)\}", lambda m: PARAMS[m.group(1)], path)
        # Forty refusals from one address would lock it out; this test is about the
        # door, not the lock (that is test_throttle / test_auth_rest).
        locked.app.state.gate.throttle.reset()
        response = await locked.request(method, url, json={})
        assert response.status_code == 401, (method, path, response.text)
        assert response.json() == UNAUTHORIZED, (method, path)
        checked += 1
    assert checked > 30
    after = (await locked.get("/api/sim/truth", headers=owner(locked))).json()
    assert {k: v["percent_now"] for k, v in after.items()} == {
        k: v["percent_now"] for k, v in before.items()
    }


def owner(client) -> dict[str, str]:
    return issue(client, "Prüfer")[1]
