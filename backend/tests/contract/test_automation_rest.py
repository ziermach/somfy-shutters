"""Automations over REST match contracts/rest.md (feature 003)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG

WEEKDAYS = [True] * 5 + [False] * 2


@pytest.fixture
def client(tmp_path):
    settings = Settings.model_validate(CONFIG)
    bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    app = create_app(settings, store=Store(tmp_path / "state.db"), bridge=bridge)
    with TestClient(app) as c:
        yield c


def body(**over) -> dict:
    b = {
        "name": "Werktags morgens",
        "days": WEEKDAYS,
        "trigger": {"kind": "time", "time": "06:45"},
        "targets": "all",
        "action": {"kind": "open"},
    }
    b.update(over)
    return b


# --- US1 ---------------------------------------------------------------------


def test_list_shape(client) -> None:
    got = client.get("/api/automations").json()
    assert set(got) == {"rules", "pause", "clock", "location"}
    assert got["rules"] == []
    assert got["pause"] == {"paused": False, "until": None}
    assert got["clock"]["reliable"] in (True, False)
    assert got["location"] is None


def test_create_returns_the_stored_rule(client) -> None:
    response = client.post("/api/automations", json=body())
    assert response.status_code == 201
    rule = response.json()
    assert rule["id"].startswith("r_")
    assert rule["name"] == "Werktags morgens"
    assert rule["days"] == WEEKDAYS
    assert rule["trigger"] == {"kind": "time", "time": "06:45"}
    assert rule["targets"] == "all"
    assert rule["action"] == {"kind": "open", "percent": None}
    assert rule["enabled"] is True and rule["skip_next"] is False
    assert rule["next"]["at"] is not None and rule["next"]["reason"] is None
    assert rule["last"] is None
    assert rule["conflicts"] == []
    assert [r["id"] for r in client.get("/api/automations").json()["rules"]] == [rule["id"]]


@pytest.mark.parametrize(
    "over",
    [
        {"targets": ["gibtsnicht"]},
        {"targets": []},
        {"action": {"kind": "position"}},
        {"trigger": {"kind": "time", "time": "06:45", "offset_minutes": 10}},
        {"trigger": {"kind": "time", "time": "6:45"}},
        {"name": ""},
        {"days": [True] * 6},
    ],
)
def test_invalid_rules_are_422_in_the_common_error_shape(client, over) -> None:
    response = client.post("/api/automations", json=body(**over))
    assert response.status_code == 422
    assert set(response.json()) == {"error", "message", "detail"}


def test_delete_is_204_and_gone(client) -> None:
    rule = client.post("/api/automations", json=body()).json()
    assert client.delete(f"/api/automations/{rule['id']}").status_code == 204
    assert client.get("/api/automations").json()["rules"] == []
    assert client.delete(f"/api/automations/{rule['id']}").status_code == 404


def test_every_change_tells_open_clients(client) -> None:
    with client.websocket_connect("/api/ws") as socket:
        socket.receive_json()  # snapshot
        rule = client.post("/api/automations", json=body()).json()
        assert socket.receive_json()["type"] == "rules_changed"
        client.delete(f"/api/automations/{rule['id']}")
        assert socket.receive_json()["type"] == "rules_changed"


# --- US2 ---------------------------------------------------------------------

SUN_TRIGGER = {"kind": "sunset", "offset_minutes": -30, "not_before": None, "not_after": None}


def test_location_round_trip_with_todays_sun_times(client) -> None:
    assert client.get("/api/location").json() is None
    got = client.put("/api/location", json={"latitude": 52.52, "longitude": 13.40}).json()
    assert got["latitude"] == 52.52 and got["longitude"] == 13.40
    assert len(got["sunrise"]) == 5 and len(got["sunset"]) == 5
    assert client.get("/api/automations").json()["location"]["sunset"] == got["sunset"]


@pytest.mark.parametrize(
    "where", [{"latitude": 91, "longitude": 0}, {"latitude": 0, "longitude": 181}, {}]
)
def test_location_out_of_range_is_422(client, where) -> None:
    response = client.put("/api/location", json=where)
    assert response.status_code == 422
    assert set(response.json()) == {"error", "message", "detail"}


def test_a_sun_rule_needs_a_location(client) -> None:
    response = client.post("/api/automations", json=body(trigger=SUN_TRIGGER))
    assert response.status_code == 409
    assert response.json()["error"] == "no_location"


def test_preview_says_what_today_resolves_to(client) -> None:
    client.put("/api/location", json={"latitude": 52.52, "longitude": 13.40})
    got = client.post("/api/automations/preview", json=body(trigger=SUN_TRIGGER)).json()
    assert set(got) == {"next", "today", "conflicts"}
    assert len(got["today"]) == 5
    assert got["next"]["at"] is not None


def test_preview_of_an_invalid_rule_is_422(client) -> None:
    response = client.post("/api/automations/preview", json=body(targets=[]))
    assert response.status_code == 422


# --- US3 ---------------------------------------------------------------------


def test_put_replaces_and_404_for_unknown(client) -> None:
    rule = client.post("/api/automations", json=body()).json()
    got = client.put(
        f"/api/automations/{rule['id']}",
        json=body(name="Später", trigger={"kind": "time", "time": "07:30"}),
    )
    assert got.status_code == 200
    assert got.json()["name"] == "Später" and got.json()["trigger"]["time"] == "07:30"
    assert got.json()["id"] == rule["id"]
    assert client.put("/api/automations/r_nope", json=body()).status_code == 404


def test_patch_enabled_keeps_everything_else(client) -> None:
    rule = client.post("/api/automations", json=body(targets=["kueche"])).json()
    off = client.patch(f"/api/automations/{rule['id']}", json={"enabled": False}).json()
    assert off["enabled"] is False
    assert off["next"] == {"at": None, "reason": "disabled"}
    # feature 004: a plain list goes in, the targets object comes back
    assert off["targets"] == {"shutters": ["kueche"], "groups": []}
    assert off["trigger"] == rule["trigger"]
    on = client.patch(f"/api/automations/{rule['id']}", json={"enabled": True}).json()
    assert on["next"]["at"] is not None


def test_firings_are_listed_newest_first_with_outcomes(client) -> None:
    rule = client.post("/api/automations", json=body(targets=["kueche"])).json()
    engine = client.app.state.automation
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    monday = datetime(2026, 9, 21, 6, 45, tzinfo=ZoneInfo("Europe/Berlin"))
    client.portal.call(engine.run_due, monday)
    client.portal.call(engine.run_due, monday + timedelta(days=1))
    got = client.get(f"/api/automations/{rule['id']}/firings").json()["firings"]
    assert [f["planned_at"][:10] for f in got] == ["2026-09-22", "2026-09-21"]
    assert got[0]["outcomes"] == [
        {"shutter_id": "kueche", "result": "commanded", "reason": None, "via": []}
    ]
    assert client.get("/api/automations").json()["rules"][0]["last"]["status"] == "fired"
    assert client.get("/api/automations/r_nope/firings").status_code == 404


def test_create_and_preview_report_conflicts(client) -> None:
    first = client.post("/api/automations", json=body(name="Auf")).json()
    clash = body(name="Zu", action={"kind": "close"})
    preview = client.post("/api/automations/preview", json=clash).json()
    assert [c["rule_id"] for c in preview["conflicts"]] == [first["id"]]
    assert preview["conflicts"][0]["winner"] == "this"
    created = client.post("/api/automations", json=clash)
    assert created.status_code == 201, "a conflict warns; it does not refuse"
    assert created.json()["conflicts"][0]["rule_name"] == "Auf"
    assert created.json()["conflicts"][0]["winner"] == created.json()["id"]


def test_rules_are_listed_by_next_firing(client) -> None:
    late = client.post(
        "/api/automations",
        json=body(name="spät", days=[True] * 7, trigger={"kind": "time", "time": "23:58"}),
    ).json()
    early = client.post(
        "/api/automations",
        json=body(name="früh", days=[True] * 7, trigger={"kind": "time", "time": "23:59"}),
    ).json()
    off = client.post("/api/automations", json=body(name="aus", enabled=False)).json()
    ids = [r["id"] for r in client.get("/api/automations").json()["rules"]]
    assert ids[-1] == off["id"], "rules that never fire go last"
    assert ids.index(late["id"]) < ids.index(early["id"])


# --- US4 ---------------------------------------------------------------------


def test_pause_until_a_time_and_resume(client) -> None:
    got = client.put("/api/automations/pause", json={"until": "2099-01-01T00:00"}).json()
    assert got["paused"] is True and got["until"].startswith("2099-01-01T00:00")
    assert client.get("/api/automations").json()["pause"]["paused"] is True
    assert client.delete("/api/automations/pause").json() == {"paused": False, "until": None}


def test_pause_until_resumed(client) -> None:
    assert client.put("/api/automations/pause", json={"until": None}).json() == {
        "paused": True,
        "until": None,
    }


def test_pause_in_the_past_is_422(client) -> None:
    response = client.put("/api/automations/pause", json={"until": "2000-01-01T00:00"})
    assert response.status_code == 422
    assert set(response.json()) == {"error", "message", "detail"}


def test_skip_next_and_nothing_to_skip(client) -> None:
    rule = client.post("/api/automations", json=body()).json()
    skipped = client.patch(f"/api/automations/{rule['id']}", json={"skip_next": True}).json()
    assert skipped["skip_next"] is True
    assert skipped["next"]["at"] == rule["next"]["at"], "the skipped firing is still shown"
    off = client.post("/api/automations", json=body(days=[False] * 7)).json()
    response = client.patch(f"/api/automations/{off['id']}", json={"skip_next": True})
    assert response.status_code == 409 and response.json()["error"] == "nothing_to_skip"


def test_editing_away_the_skipped_instant_clears_the_skip(client) -> None:
    rule = client.post("/api/automations", json=body()).json()
    client.patch(f"/api/automations/{rule['id']}", json={"skip_next": True})
    edited = client.put(
        f"/api/automations/{rule['id']}", json=body(trigger={"kind": "time", "time": "07:15"})
    ).json()
    assert edited["skip_next"] is False
    assert client.app.state.automation.store.rule(rule["id"]).skip_planned_at is None


def test_a_pause_change_tells_open_clients(client) -> None:
    with client.websocket_connect("/api/ws") as socket:
        assert socket.receive_json()["data"]["automations"]["paused"] is False
        client.put("/api/automations/pause", json={"until": None})
        frame = socket.receive_json()
        assert frame["type"] == "automations" and frame["paused"] is True


# --- simulator ---------------------------------------------------------------


def test_sim_clock_forces_the_verdict_and_returns_to_the_real_check(client) -> None:
    held = client.post("/api/sim/clock", json={"reliable": False}).json()
    assert held["clock_reliable"] is False
    assert client.get("/api/automations").json()["clock"]["reliable"] is False
    back = client.post("/api/sim/clock", json={"reliable": None}).json()
    assert back["clock_reliable"] is True


def test_sim_loss_rate_can_be_set_and_is_bounded(client) -> None:
    assert client.post("/api/sim/loss", json={"rate": 0.5}).json() == {"loss_rate": 0.5}
    assert client.app.state.bridge.loss_rate == 0.5
    assert client.post("/api/sim/loss", json={"rate": 1.5}).status_code == 422


# --- feature 004: groups as targets --------------------------------------------------


def group(client, name, *members) -> str:
    response = client.post("/api/groups", json={"name": name, "members": list(members)})
    assert response.status_code == 201
    return response.json()["id"]


def test_targets_object_round_trips(client) -> None:
    gid = group(client, "Erdgeschoss", "wohnzimmer", "kueche")
    targets = {"shutters": ["schlafzimmer"], "groups": [gid]}
    rule = client.post("/api/automations", json=body(targets=targets)).json()
    assert rule["targets"] == targets
    assert client.get("/api/automations").json()["rules"][0]["targets"] == targets


def test_unknown_group_is_422(client) -> None:
    response = client.post("/api/automations", json=body(targets={"groups": ["g_nope"]}))
    assert response.status_code == 422
    assert response.json()["error"] == "unknown_group"
    assert response.json()["detail"] == {"groups": ["g_nope"]}


def test_empty_targets_object_is_422(client) -> None:
    response = client.post("/api/automations", json=body(targets={"shutters": [], "groups": []}))
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_rule"


def test_firing_history_says_which_group_reached_each_shutter(client) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    eg = group(client, "Erdgeschoss", "wohnzimmer", "kueche")
    sued = group(client, "Südseite", "wohnzimmer", "schlafzimmer")
    rule = client.post("/api/automations", json=body(targets={"groups": [eg, sued]})).json()
    monday = datetime(2026, 9, 21, 6, 45, tzinfo=ZoneInfo("Europe/Berlin"))
    client.portal.call(client.app.state.automation.run_due, monday)
    [firing] = client.get(f"/api/automations/{rule['id']}/firings").json()["firings"]
    via = {o["shutter_id"]: o["via"] for o in firing["outcomes"]}
    assert via == {
        "wohnzimmer": ["Erdgeschoss", "Südseite"],
        "kueche": ["Erdgeschoss"],
        "schlafzimmer": ["Südseite"],
    }


def test_deleting_a_group_removes_it_from_rules(client) -> None:
    gid = group(client, "Südseite", "wohnzimmer")
    rule = client.post("/api/automations", json=body(targets={"groups": [gid]})).json()
    seen: list[str] = []

    async def listen(event: dict) -> None:
        seen.append(event["type"])

    client.app.state.bus.subscribe(listen)
    assert client.delete(f"/api/groups/{gid}").status_code == 204
    [after] = client.get("/api/automations").json()["rules"]
    assert after["id"] == rule["id"]
    assert after["targets"] == {"shutters": [], "groups": []}
    assert after["next"] == {"at": None, "reason": "no_targets"}
    assert "rules_changed" in seen


def test_conflict_names_the_group_it_comes_through(client) -> None:
    gid = group(client, "Erdgeschoss", "wohnzimmer", "kueche")
    client.post("/api/automations", json=body(name="A", targets=["kueche"]))
    rule = client.post(
        "/api/automations",
        json=body(name="B", targets={"groups": [gid]}, action={"kind": "close"}),
    ).json()
    [c] = rule["conflicts"]
    assert c["rule_name"] == "A" and c["shutter_id"] == "kueche" and c["via"] == "Erdgeschoss"


def test_saving_a_group_warns_about_the_conflict_it_creates(client) -> None:
    """FR-028: quickstart D6."""
    gid = group(client, "Südseite", "wohnzimmer")
    client.post("/api/automations", json=body(name="A", targets=["kueche"]))
    client.post(
        "/api/automations",
        json=body(name="B", targets={"groups": [gid]}, action={"kind": "close"}),
    )
    response = client.put(
        f"/api/groups/{gid}", json={"name": "Südseite", "members": ["wohnzimmer", "kueche"]}
    )
    assert response.status_code == 200
    [c] = response.json()["conflicts"]
    assert set(c) == {
        "rule_id",
        "rule_name",
        "other_rule_id",
        "other_rule_name",
        "shutter_id",
        "via",
        "first_at",
        "winner",
    }
    assert {c["rule_name"], c["other_rule_name"]} == {"A", "B"}
    assert c["shutter_id"] == "kueche" and c["via"] == "Südseite"
    assert response.json()["members"] == ["wohnzimmer", "kueche"]  # saved regardless
