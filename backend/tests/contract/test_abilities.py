"""T027: a credential can do less than everything (user story 3, FR-010, FR-011)."""

from __future__ import annotations

import pytest

from somfy_shutters.auth.models import Ability

from .locked import issue, locked, only  # noqa: F401 — fixture

# One route per ability, each harmless to call with this body.
ROUTE = {
    Ability.WATCH: ("GET", "/api/shutters", None),
    Ability.COMMAND: ("POST", "/api/shutters/wohnzimmer/command", {"action": "stop"}),
    Ability.CONFIGURE: ("PUT", "/api/location", {"latitude": 52.5, "longitude": 13.4}),
    Ability.CALIBRATE: ("DELETE", "/api/calibration/wohnzimmer/run", None),
    Ability.MANAGE: ("GET", "/api/auth/credentials", None),
}


@pytest.mark.parametrize("held", list(Ability))
async def test_each_ability_opens_its_own_routes_and_no_others(locked, held) -> None:  # noqa: F811
    _, headers, _ = issue(locked, f"nur {held}", abilities=only(held))
    for ability, (method, url, body) in ROUTE.items():
        response = await locked.request(method, url, json=body, headers=headers)
        if ability in (held, Ability.WATCH):
            assert response.status_code != 403, (held, ability, response.text)
        else:
            assert response.status_code == 403, (held, ability, response.text)
            assert response.json()["error"] == "forbidden"
            assert response.json()["detail"] == {"needs": ability.value}


async def test_a_refusal_is_recorded(locked) -> None:  # noqa: F811
    _, headers, _ = issue(locked, "Zuschauer", abilities=only(Ability.WATCH))
    await locked.post("/api/shutters/wohnzimmer/command", json={"action": "open"}, headers=headers)
    [entry] = [e for e in locked.app.state.audit.query() if e.outcome == "refused_permission"]
    assert entry.actor.name == "Zuschauer" and entry.shutter_id == "wohnzimmer"
    assert entry.detail["needs"] == "command"


@pytest.mark.parametrize("path", ["/api/auth/credentials", "/api/auth/pairing"])
async def test_nobody_hands_on_more_than_they_hold(locked, path) -> None:  # noqa: F811
    _, headers, _ = issue(locked, "Halb", abilities=only(Ability.MANAGE, Ability.COMMAND))
    body = {"abilities": ["command", "calibrate"]}
    if path.endswith("credentials"):
        body["name"] = "Mehr"
    response = await locked.post(path, json=body, headers=headers)
    assert response.status_code == 403
    assert response.json()["error"] == "exceeds_own"
    assert response.json()["detail"] == {"abilities": ["calibrate"]}
    body["abilities"] = ["command"]
    assert (await locked.post(path, json=body, headers=headers)).status_code == 201
