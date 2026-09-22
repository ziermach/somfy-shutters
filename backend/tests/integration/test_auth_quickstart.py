"""quickstart.md of feature 008, walked end to end by machine.

The single refusals are proven in tests/contract; here the scenarios run as a
household would live them: the Pi prints a code, the laptop pairs, the laptop
pairs a phone, the owner locks themselves out and gets back in.
"""

from __future__ import annotations

import re
import statistics
import time

from fastapi.testclient import TestClient

from somfy_shutters import cli
from somfy_shutters.auth.models import ALL_ABILITIES
from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG

ORIGIN = "http://testserver"


def house(db, mode: str | None = "required") -> TestClient:
    auth = {"mode": mode} if mode else {}
    settings = Settings.model_validate({**CONFIG, "auth": auth})
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    return TestClient(create_app(settings, store=Store(db), bridge=bridge))


def recover(db, monkeypatch, capsys, tmp_path) -> str:
    config = tmp_path / "shutters.toml"
    if not config.exists():
        config.write_text(
            '[auth]\nmode = "required"\n[[shutter]]\nid = "wohnzimmer"\nname = "W"\n'
            'address = "0x279621"\n',
            encoding="utf-8",
        )
    monkeypatch.setenv("SHUTTERS_CONFIG", str(config))
    monkeypatch.setenv("SHUTTERS_DB", str(db))
    assert cli.main(["auth", "recover"]) == 0
    return re.search(r"Kopplungscode: (\w{3}-\w{3})", capsys.readouterr().out).group(1)


def test_a_household_from_first_run_to_lockout_and_back(tmp_path, monkeypatch, capsys) -> None:
    db = tmp_path / "state.db"
    with house(db) as laptop:
        # A1/A2: the door is shut, the feed says nothing.
        assert laptop.get("/api/shutters").status_code == 401
        # F: first run is recovery — the Pi prints a code, the laptop pairs once.
        code = recover(db, monkeypatch, capsys, tmp_path)
        assert (
            laptop.post("/api/auth/pair", json={"code": code, "name": "Laptop"}).status_code == 201
        )
        # A4: from now on the laptop just works, no screen asks again.
        write = {"Origin": ORIGIN}
        assert (
            laptop.post(
                "/api/shutters/wohnzimmer/command", json={"action": "close"}, headers=write
            ).status_code
            == 200
        )
        with laptop.websocket_connect("/api/ws", headers=write) as ws:
            assert ws.receive_json()["type"] == "snapshot"

        # D1: the laptop pairs Anna's phone, which may only watch and command.
        minted = laptop.post(
            "/api/auth/pairing", json={"abilities": ["command"]}, headers=write
        ).json()
        # (token: true — this client keeps the laptop's cookie; a phone would get its own)
        anna = laptop.post(
            "/api/auth/pair", json={"code": minted["code"], "name": "Anna", "token": True}
        )
        assert anna.json()["credential"]["abilities"] == ["watch", "command"]
        anna_headers = {"Authorization": f"Bearer {anna.json()['token']}"}
        assert laptop.get("/api/auth/credentials", headers=anna_headers).status_code == 403

        # E1: the record says who did what.
        entries = laptop.get("/api/audit").json()["entries"]
        assert any(e["action"] == "command" and e["actor"]["name"] == "Laptop" for e in entries)
        assert any(e["action"] == "recovery" for e in entries)

        # F1: revoking everything needs a confirmation, then the laptop is out.
        me = laptop.get("/api/auth/me").json()["id"]
        others = [
            c["id"]
            for c in laptop.get("/api/auth/credentials").json()["credentials"]
            if c["id"] != me
        ]
        for other in others:
            laptop.request("DELETE", f"/api/auth/credentials/{other}", headers=write)
        assert (
            laptop.request("DELETE", f"/api/auth/credentials/{me}", headers=write).status_code
            == 409
        )
        assert (
            laptop.request(
                "DELETE",
                f"/api/auth/credentials/{me}",
                json={"confirm_lockout": True},
                headers=write,
            ).status_code
            == 204
        )
        assert laptop.get("/api/shutters").status_code == 401

        # …and back in from the Pi, with everything intact.
        code = recover(db, monkeypatch, capsys, tmp_path)
        assert (
            laptop.post("/api/auth/pair", json={"code": code, "name": "Laptop"}).status_code == 201
        )
        assert laptop.get("/api/shutters").status_code == 200
        assert len(laptop.get("/api/audit").json()["entries"]) >= len(entries)


def test_h1_the_simulator_runs_open_by_default(tmp_path) -> None:
    with house(tmp_path / "state.db", mode=None) as client:
        assert client.get("/api/auth/me").json()["mode"] == "open"
        assert (
            client.post("/api/shutters/wohnzimmer/command", json={"action": "close"}).status_code
            == 200
        )


def test_sc004_a_credential_costs_a_command_almost_nothing(tmp_path) -> None:
    """Median command time with a bearer credential within 5 ms of the simulator's open mode."""

    def median(client, headers) -> float:
        times = []
        for i in range(200):
            client.app.state.gate.throttle.reset()
            start = time.perf_counter()
            client.post(
                "/api/shutters/wohnzimmer/command",
                json={"action": "open" if i % 2 else "close"},
                headers=headers,
            )
            times.append(time.perf_counter() - start)
        return statistics.median(times)

    with house(tmp_path / "open.db", mode=None) as open_house:
        baseline = median(open_house, {})
    with house(tmp_path / "shut.db") as shut_house:
        _, token = shut_house.app.state.auth.issue("Laptop", ALL_ABILITIES)
        guarded = median(shut_house, {"Authorization": f"Bearer {token}"})
    assert guarded - baseline < 0.005, (guarded, baseline)
