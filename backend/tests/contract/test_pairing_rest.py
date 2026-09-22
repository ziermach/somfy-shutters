"""T030: adding a phone without typing a long secret (user story 4, FR-030 to FR-035)."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime

from .locked import issue, locked  # noqa: F401 — fixture


def actions(client) -> list[str]:
    return [e.action for e in client.app.state.audit.query(limit=200)]


async def mint(client, headers, abilities=("watch", "command")) -> dict:
    response = await client.post(
        "/api/auth/pairing", json={"abilities": list(abilities)}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_mint_redeem_and_the_new_device_is_its_own(locked) -> None:  # noqa: F811
    owner, headers, _ = issue(locked)
    minted = await mint(locked, headers)
    assert re.fullmatch(r"[0-9A-Z]{3}-[0-9A-Z]{3}", minted["code"])
    expires = datetime.fromisoformat(minted["expires_at"])
    created = locked.app.state.auth.code(minted["id"]).created_at
    assert round((expires - created).total_seconds()) == 300
    listed = (await locked.get("/api/auth/pairing", headers=headers)).json()["codes"]
    assert [c["id"] for c in listed] == [minted["id"]] and "code" not in listed[0]

    response = await locked.post(
        "/api/auth/pair", json={"code": minted["code"], "name": "Anna", "token": True}
    )
    anna = response.json()["credential"]
    assert anna["abilities"] == ["watch", "command"] and anna["origin"] == "paired"
    assert locked.app.state.auth.get(anna["id"]).created_by == owner.id
    assert "pairing_minted" in actions(locked) and "pairing_redeemed" in actions(locked)


async def test_a_code_works_once(locked) -> None:  # noqa: F811
    _, headers, _ = issue(locked)
    minted = await mint(locked, headers)
    first = await locked.post("/api/auth/pair", json={"code": minted["code"], "name": "A"})
    second = await locked.post("/api/auth/pair", json={"code": minted["code"], "name": "B"})
    assert (first.status_code, second.status_code) == (201, 401)
    assert "pairing_failed" in actions(locked)


async def test_cancelled_and_orphaned_codes_are_refused(locked) -> None:  # noqa: F811
    _, headers, _ = issue(locked)
    minted = await mint(locked, headers)
    assert (
        await locked.delete(f"/api/auth/pairing/{minted['id']}", headers=headers)
    ).status_code == 204
    assert (
        await locked.post("/api/auth/pair", json={"code": minted["code"], "name": "x"})
    ).status_code == 401
    assert (
        await locked.delete(f"/api/auth/pairing/{minted['id']}", headers=headers)
    ).status_code == 404

    minter, minter_headers, _ = issue(locked, "Minter")
    orphan = await mint(locked, minter_headers)
    await locked.delete(f"/api/auth/credentials/{minter.id}", headers=headers)
    assert (
        await locked.post("/api/auth/pair", json={"code": orphan["code"], "name": "x"})
    ).status_code == 401


async def test_two_devices_racing_for_one_code(locked) -> None:  # noqa: F811
    _, headers, _ = issue(locked)
    minted = await mint(locked, headers)
    results = await asyncio.gather(
        *(locked.post("/api/auth/pair", json={"code": minted["code"], "name": n}) for n in "AB")
    )
    assert sorted(r.status_code for r in results) == [201, 401]


async def test_ten_wrong_codes_cancel_the_outstanding_one(locked) -> None:  # noqa: F811
    _, headers, _ = issue(locked)
    minted = await mint(locked, headers)
    for i in range(10):
        await locked.post("/api/auth/pair", json={"code": f"00000{i}", "name": "x"})
    assert (await locked.get("/api/auth/pairing", headers=headers)).json()["codes"] == []
    assert (
        await locked.post("/api/auth/pair", json={"code": minted["code"], "name": "x"})
    ).status_code == 401
    cancelled = [
        e for e in locked.app.state.audit.query(limit=200) if e.action == "pairing_cancelled"
    ]
    assert [e.detail for e in cancelled] == [{"by": "guessing"}]
