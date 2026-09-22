"""T044: guessing and flooding over the real surface (user story 7, FR-021 to FR-024)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from starlette.websockets import WebSocketDisconnect

from somfy_shutters.auth.models import ALL_ABILITIES
from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from .locked import ORIGIN, issue, locked, required_settings  # noqa: F401 — fixture

BAD = {"Authorization": "Bearer sst_" + "A" * 52}


def from_address(app, host: str) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app, client=(host, 1234)), base_url=ORIGIN)


async def test_eleventh_failure_locks_the_address_even_for_a_valid_token(locked) -> None:  # noqa: F811
    _, good, _ = issue(locked)
    async with (
        from_address(locked.app, "10.0.0.66") as attacker,
        from_address(locked.app, "10.0.0.7") as neighbour,
    ):
        for _ in range(10):
            assert (await attacker.get("/api/shutters", headers=BAD)).status_code == 401
        locked_out = await attacker.get("/api/shutters", headers=good)
        assert locked_out.status_code == 429
        assert int(locked_out.headers["Retry-After"]) > 800
        assert locked_out.json()["error"] == "throttled"
        assert (await neighbour.get("/api/shutters", headers=good)).status_code == 200


async def test_the_lockout_ignores_the_wall_clock(locked) -> None:  # noqa: F811
    """A Pi whose clock is corrected by hours mid-lockout neither frees nor traps anyone."""
    _, good, _ = issue(locked)
    async with from_address(locked.app, "10.0.0.66") as attacker:
        for _ in range(10):
            await attacker.get("/api/shutters", headers=BAD)
        auth = locked.app.state.auth
        wall = auth.clock()
        auth.clock = lambda: wall - timedelta(hours=6)
        assert (await attacker.get("/api/shutters", headers=good)).status_code == 429
        auth.clock = lambda: wall + timedelta(hours=6)
        assert (await attacker.get("/api/shutters", headers=good)).status_code == 429


async def test_a_command_flood_stops_before_the_bridge(locked) -> None:  # noqa: F811
    _, headers, _ = issue(locked)
    bridge = locked.app.state.bridge
    sent: list[str] = []
    real = bridge.send_level

    async def counted(address: str, percent: int) -> None:
        sent.append(address)
        await real(address, percent)

    bridge.send_level = counted
    statuses = []
    for i in range(30):
        action = "open" if i % 2 else "close"
        response = await locked.post(
            "/api/shutters/wohnzimmer/command", json={"action": action}, headers=headers
        )
        statuses.append(response.status_code)
    accepted = statuses.count(200)
    assert 10 <= accepted <= 12 and statuses.count(429) == 30 - accepted
    assert len(sent) == accepted
    refused = [
        e for e in locked.app.state.audit.query(limit=200) if e.outcome == "refused_throttle"
    ]
    assert len(refused) == 30 - accepted


async def test_a_permission_refusal_does_not_spend_the_bucket(locked) -> None:  # noqa: F811
    from somfy_shutters.auth.models import Ability

    from .locked import only

    _, headers, _ = issue(locked, abilities=only(Ability.WATCH))
    for _ in range(15):
        response = await locked.post(
            "/api/shutters/wohnzimmer/command", json={"action": "stop"}, headers=headers
        )
        assert response.status_code == 403


async def test_forwarded_for_is_believed_only_from_the_trusted_proxy(tmp_path) -> None:
    settings = required_settings(trusted_proxy="10.0.0.1")
    app = create_app(
        settings,
        store=Store(tmp_path / "s.db"),
        bridge=SimBridge(addresses=[s.address for s in settings.shutter]),
    )
    async with app.router.lifespan_context(app):
        async with from_address(app, "10.0.0.1") as proxy:
            for i in range(10):
                await proxy.get(
                    "/api/shutters", headers={**BAD, "X-Forwarded-For": f"203.0.113.{i}"}
                )
            # ten different clients behind the proxy: none locked out
            assert app.state.gate.throttle.locked("203.0.113.1") is None
            assert app.state.gate.throttle.locked("10.0.0.1") is None
        async with from_address(app, "10.0.0.99") as liar:
            for _ in range(10):
                await liar.get("/api/shutters", headers={**BAD, "X-Forwarded-For": "1.2.3.4"})
            assert app.state.gate.throttle.locked("10.0.0.99") is not None
            assert app.state.gate.throttle.locked("1.2.3.4") is None


async def test_guessing_pairing_codes_locks_the_address(locked) -> None:  # noqa: F811
    """Quickstart G4 (FR-033)."""
    async with from_address(locked.app, "10.0.0.66") as guesser:
        for i in range(10):
            response = await guesser.post("/api/auth/pair", json={"code": f"00000{i}", "name": "x"})
            assert response.status_code == 401
        eleventh = await guesser.post("/api/auth/pair", json={"code": "000009", "name": "x"})
        assert eleventh.status_code == 429


def test_a_locked_address_gets_4429_on_the_feed(tmp_path) -> None:
    settings = required_settings()
    app = create_app(
        settings,
        store=Store(tmp_path / "s.db"),
        bridge=SimBridge(addresses=[s.address for s in settings.shutter]),
    )
    with TestClient(app) as client:
        _, token = app.state.auth.issue("Owner", ALL_ABILITIES)
        for _ in range(10):
            client.get("/api/shutters", headers=BAD)
        with (
            pytest.raises(WebSocketDisconnect) as caught,
            client.websocket_connect("/api/ws", headers={"Authorization": f"Bearer {token}"}) as ws,
        ):
            ws.receive_json()
        assert caught.value.code == 4429
