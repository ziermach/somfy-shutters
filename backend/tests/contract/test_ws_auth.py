"""T013, T023: the live feed says nothing to a stranger (contracts/websocket.md)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from somfy_shutters.auth.models import ALL_ABILITIES
from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from .locked import required_settings

ORIGIN = "http://testserver"


@pytest.fixture
def app_client(tmp_path):
    settings = required_settings()
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    with TestClient(app) as client:
        yield client


def token_for(client, name="Owner") -> tuple:
    credential, token = client.app.state.auth.issue(name, ALL_ABILITIES)
    return credential, token


def closed_with(client, **kw) -> int:
    with (
        pytest.raises(WebSocketDisconnect) as caught,
        client.websocket_connect("/api/ws", **kw) as ws,
    ):
        ws.receive_json()
    return caught.value.code


def test_no_credential_closes_4401_before_any_frame(app_client) -> None:
    assert closed_with(app_client) == 4401


def test_a_bad_token_closes_4401(app_client) -> None:
    assert closed_with(app_client, headers={"Authorization": "Bearer sst_nope"}) == 4401


def test_a_cookie_from_a_foreign_page_closes_4401(app_client) -> None:
    _, token = token_for(app_client)
    app_client.cookies.set("sst", token)
    assert closed_with(app_client, headers={"Origin": "http://evil.example"}) == 4401


def test_bearer_or_cookie_gets_the_snapshot(app_client) -> None:
    _, token = token_for(app_client)
    with app_client.websocket_connect(
        "/api/ws", headers={"Authorization": f"Bearer {token}"}
    ) as ws:
        assert ws.receive_json()["type"] == "snapshot"
    app_client.cookies.set("sst", token)
    with app_client.websocket_connect("/api/ws", headers={"Origin": ORIGIN}) as ws:
        assert ws.receive_json()["type"] == "snapshot"


def test_revoking_closes_that_feed_and_only_that_feed(app_client) -> None:
    a, token_a = token_for(app_client, "A")
    _, token_b = token_for(app_client, "B")
    with (
        app_client.websocket_connect(
            "/api/ws", headers={"Authorization": f"Bearer {token_a}"}
        ) as wa,
        app_client.websocket_connect(
            "/api/ws", headers={"Authorization": f"Bearer {token_b}"}
        ) as wb,
    ):
        wa.receive_json()
        wb.receive_json()
        response = app_client.delete(
            f"/api/auth/credentials/{a.id}", headers={"Authorization": f"Bearer {token_b}"}
        )
        assert response.status_code == 204
        with pytest.raises(WebSocketDisconnect) as caught:
            wa.receive_json()
        assert caught.value.code == 4401
        assert app_client.app.state.hub.owners() == {
            c.id for c in app_client.app.state.auth.list() if c.name == "B"
        }


def test_an_expired_credentials_feed_closes_on_the_sweep(app_client) -> None:
    from datetime import UTC, datetime, timedelta

    auth = app_client.app.state.auth
    soon = datetime.now(UTC) + timedelta(seconds=30)
    credential, token = auth.issue("Gast", ALL_ABILITIES, expires_at=soon)
    with app_client.websocket_connect(
        "/api/ws", headers={"Authorization": f"Bearer {token}"}
    ) as ws:
        ws.receive_json()
        auth.clock = lambda: soon + timedelta(seconds=1)
        app_client.portal.call(app_client.app.state.sweep_auth, soon - timedelta(seconds=30), soon)
        with pytest.raises(WebSocketDisconnect) as caught:
            ws.receive_json()
        assert caught.value.code == 4401
    [entry] = [e for e in app_client.app.state.audit.query() if e.action == "credential_expired"]
    assert entry.target == credential.id
