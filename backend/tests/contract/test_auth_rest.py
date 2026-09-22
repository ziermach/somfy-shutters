"""T012 and later: the door, credentials and throttling over REST (contracts/rest.md)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from somfy_shutters.auth.models import Ability

from .locked import ORIGIN, issue, locked, only  # noqa: F401 — fixture

UNAUTHORIZED = {
    "error": "unauthorized",
    "message": "Dieses Gerät ist nicht angemeldet.",
    "detail": None,
}


def entries(client, action: str | None = None) -> list:
    found = client.app.state.audit.query(limit=200)
    return [e for e in found if action is None or e.action == action]


# --- US1: every kind of bad looks the same ----------------------------------------


async def test_every_bad_credential_gets_the_same_refusal(locked) -> None:  # noqa: F811
    revoked, _, revoked_token = issue(locked, "Weg")
    locked.app.state.auth.revoke(revoked.id, by=None)
    _, _, expired_token = issue(locked, "Alt", expires_at=datetime.now(UTC) - timedelta(seconds=1))
    headers = [
        {},
        {"Authorization": "Bearer sst_" + "A" * 52},
        {"Authorization": "Bearer nonsense"},
        {"Authorization": f"Bearer {expired_token}"},
        {"Authorization": f"Bearer {revoked_token}"},
    ]
    bodies = []
    for h in headers:
        response = await locked.get("/api/shutters", headers=h)
        assert response.status_code == 401
        bodies.append(response.content)
    assert len(set(bodies)) == 1
    assert locked.app.state.audit.query()[0].action == "auth_failed"
    reasons = [e.detail["reason"] for e in entries(locked, "auth_failed")]
    assert sorted(reasons) == ["expired", "malformed", "none", "revoked", "unknown"]


async def test_a_valid_credential_changes_nothing(locked) -> None:  # noqa: F811
    _, headers, _ = issue(locked)
    response = await locked.post(
        "/api/shutters/wohnzimmer/command", json={"action": "close"}, headers=headers
    )
    assert response.status_code == 200 and response.json()["accepted"] is True


async def test_a_cookie_needs_its_own_origin_to_change_anything(locked) -> None:  # noqa: F811
    _, _, token = issue(locked)
    locked.cookies.set("sst", token)
    command = {"action": "close"}
    url = "/api/shutters/wohnzimmer/command"
    assert (await locked.get("/api/shutters")).status_code == 200  # reading is fine
    missing = await locked.post(url, json=command)
    foreign = await locked.post(url, json=command, headers={"Origin": "http://evil.example"})
    assert missing.status_code == foreign.status_code == 403
    assert foreign.json()["error"] == "bad_origin"
    assert (await locked.post(url, json=command, headers={"Origin": ORIGIN})).status_code == 200


async def test_a_bearer_needs_no_origin(locked) -> None:  # noqa: F811
    _, headers, _ = issue(locked)
    response = await locked.post(
        "/api/shutters/wohnzimmer/command", json={"action": "open"}, headers=headers
    )
    assert response.status_code == 200


async def test_health_says_nothing_to_strangers_and_counts_nothing(locked) -> None:  # noqa: F811
    before = len(entries(locked))
    for h in ({}, {"Authorization": "Bearer nonsense"}):
        for _ in range(10):
            assert (await locked.get("/api/health", headers=h)).json() == {"status": "ok"}
    assert len(entries(locked)) == before
    _, headers, _ = issue(locked, abilities=only(Ability.WATCH))
    full = (await locked.get("/api/health", headers=headers)).json()
    assert set(full) == {"status", "bridge", "shutters"}


async def test_me(locked) -> None:  # noqa: F811
    credential, headers, _ = issue(locked, "Küche", abilities=only(Ability.COMMAND))
    me = (await locked.get("/api/auth/me", headers=headers)).json()
    assert me["id"] == credential.id and me["name"] == "Küche"
    assert me["abilities"] == ["watch", "command"] and me["mode"] == "required"
    assert me["is_me"] is True


async def test_me_in_open_mode(client) -> None:
    me = (await client.get("/api/auth/me")).json()
    assert me["mode"] == "open" and me["origin"] == "simulator"
    assert me["abilities"] == ["watch", "command", "configure", "calibrate", "manage"]


# --- US1: pairing a device ---------------------------------------------------------


async def test_pairing_sets_a_cookie_that_works(locked) -> None:  # noqa: F811
    record, code = locked.app.state.auth.mint(only(Ability.COMMAND), None, 15)
    response = await locked.post("/api/auth/pair", json={"code": code.lower(), "name": "Laptop"})
    assert response.status_code == 201
    cookie = response.headers["set-cookie"]
    assert "sst=sst_" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Max-Age=315360000" in cookie and "Secure" not in cookie
    assert response.json()["credential"]["name"] == "Laptop"
    assert "token" not in response.json()
    assert (await locked.get("/api/shutters")).status_code == 200  # the cookie is kept
    assert entries(locked, "pairing_redeemed")[0].target == record.id


async def test_pairing_can_hand_back_a_token_instead(locked) -> None:  # noqa: F811
    _, code = locked.app.state.auth.mint(only(Ability.WATCH), None, 15)
    response = await locked.post(
        "/api/auth/pair", json={"code": code, "name": "Skript", "token": True}
    )
    token = response.json()["token"]
    assert "set-cookie" not in response.headers
    ok = await locked.get("/api/shutters", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200


async def test_a_bad_code_is_one_refusal_recorded_once(locked) -> None:  # noqa: F811
    response = await locked.post("/api/auth/pair", json={"code": "000000", "name": "x"})
    assert response.status_code == 401 and response.json() == UNAUTHORIZED
    assert len(entries(locked, "pairing_failed")) == 1
    assert entries(locked, "auth_failed") == []


async def test_malformed_pairing_is_422_and_not_counted(locked) -> None:  # noqa: F811
    assert (
        await locked.post("/api/auth/pair", json={"code": "12", "name": "x"})
    ).status_code == 422
    assert (await locked.post("/api/auth/pair", json={"code": "000000"})).status_code == 422
    assert entries(locked, "pairing_failed") == []


# --- US2: one per device, revocable alone ---------------------------------------------


async def test_issue_shows_the_token_once(locked) -> None:  # noqa: F811
    _, headers, _ = issue(locked)
    response = await locked.post(
        "/api/auth/credentials", json={"name": "Handy A", "abilities": ["command"]}, headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["token"].startswith("sst_") and body["abilities"] == ["watch", "command"]
    ok = await locked.get("/api/shutters", headers={"Authorization": f"Bearer {body['token']}"})
    assert ok.status_code == 200
    assert entries(locked, "credential_issued")[0].target == body["id"]


async def test_the_list_never_shows_a_secret(locked) -> None:  # noqa: F811
    _, headers, token = issue(locked)
    issue(locked, "Handy B")
    listed = await locked.get("/api/auth/credentials", headers=headers)
    text = listed.text
    assert "sst_" not in text and token not in text
    assert not re.search(r"[0-9a-f]{64}", text)
    [mine] = [c for c in listed.json()["credentials"] if c["is_me"]]
    assert set(mine) == {
        "id",
        "name",
        "abilities",
        "origin",
        "created_at",
        "last_used_at",
        "expires_at",
        "revoked_at",
        "state",
        "is_me",
    }


async def test_revoking_one_leaves_the_other(locked) -> None:  # noqa: F811
    _, owner_headers, _ = issue(locked)
    a, a_headers, _ = issue(locked, "Handy A", abilities=only(Ability.COMMAND))
    _, b_headers, _ = issue(locked, "Handy B", abilities=only(Ability.COMMAND))
    response = await locked.delete(f"/api/auth/credentials/{a.id}", headers=owner_headers)
    assert response.status_code == 204
    assert (await locked.get("/api/shutters", headers=a_headers)).status_code == 401
    assert (await locked.get("/api/shutters", headers=b_headers)).status_code == 200
    listed = (await locked.get("/api/auth/credentials", headers=owner_headers)).json()
    assert {c["name"]: c["state"] for c in listed["credentials"]}["Handy A"] == "revoked"
    assert entries(locked, "credential_revoked")[0].target == a.id


async def test_revoking_an_unknown_credential_is_404(locked) -> None:  # noqa: F811
    _, headers, _ = issue(locked)
    response = await locked.delete("/api/auth/credentials/c_nope", headers=headers)
    assert response.status_code == 404 and response.json()["error"] == "unknown_credential"


async def test_invalid_credential_is_422(locked) -> None:  # noqa: F811
    _, headers, _ = issue(locked)
    for body in (
        {"name": "", "abilities": ["watch"]},
        {"name": "x" * 41, "abilities": ["watch"]},
        {"name": "x", "abilities": ["fly"]},
        {"name": "x", "abilities": []},
    ):
        response = await locked.post("/api/auth/credentials", json=body, headers=headers)
        assert response.status_code == 422 and response.json()["error"] == "invalid_credential"
