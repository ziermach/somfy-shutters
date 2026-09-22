"""T011, T020: the groups REST surface matches specs/004-shutter-groups/contracts/rest.md."""

from __future__ import annotations

import pytest

ERROR_KEYS = {"error", "message", "detail"}


@pytest.fixture
def frames(client) -> list[dict]:
    """Every `groups` event the app publishes, in order."""
    seen: list[dict] = []

    async def listen(event: dict) -> None:
        if event.get("type") == "groups":
            seen.append(event)

    client.app.state.bus.subscribe(listen)
    return seen


async def make(client, name: str, *members: str) -> dict:
    response = await client.post("/api/groups", json={"name": name, "members": list(members)})
    assert response.status_code == 201, response.json()
    return response.json()


# --- US1: create, edit, order, delete ------------------------------------------


async def test_empty_to_begin_with(client) -> None:
    assert (await client.get("/api/groups")).json() == {"groups": []}


async def test_create_returns_the_group_and_appends_it(client, frames) -> None:
    first = await make(client, "Erdgeschoss", "wohnzimmer", "kueche")
    assert set(first) >= {"id", "name", "members", "conflicts"}
    assert first["members"] == ["wohnzimmer", "kueche"]
    await make(client, "Südseite", "wohnzimmer", "schlafzimmer")
    listed = (await client.get("/api/groups")).json()["groups"]
    assert [g["name"] for g in listed] == ["Erdgeschoss", "Südseite"]
    assert set(listed[0]) == {"id", "name", "members"}
    assert len(frames) == 2
    assert frames[-1]["groups"] == listed


async def test_name_taken_ignores_case_and_whitespace(client, frames) -> None:
    first = await make(client, "Südseite", "kueche")
    response = await client.post("/api/groups", json={"name": "  südseite ", "members": ["kueche"]})
    assert response.status_code == 409
    body = response.json()
    assert set(body) == ERROR_KEYS
    assert body["error"] == "name_taken"
    assert body["message"] == "Diesen Namen gibt es schon."
    assert body["detail"] == {"group_id": first["id"]}
    assert len(frames) == 1


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"name": "", "members": ["kueche"]}, "name"),
        ({"name": "x" * 41, "members": ["kueche"]}, "name"),
        ({"name": "A", "members": []}, "members"),
        ({"name": "A", "members": ["kueche", "kueche"]}, "members"),
    ],
)
async def test_invalid_group(client, body, field) -> None:
    response = await client.post("/api/groups", json=body)
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_group"
    assert response.json()["detail"]["field"] == field
    assert response.json()["detail"]["problem"]


async def test_unknown_shutter(client) -> None:
    response = await client.post("/api/groups", json={"name": "A", "members": ["keller", "kueche"]})
    assert response.status_code == 422
    assert response.json()["error"] == "unknown_shutter"
    assert response.json()["detail"] == {"shutters": ["keller"]}


async def test_put_replaces_name_and_members_in_order(client, frames) -> None:
    made = await make(client, "Oben", "schlafzimmer")
    response = await client.put(
        f"/api/groups/{made['id']}", json={"name": "OG", "members": ["kueche", "schlafzimmer"]}
    )
    assert response.status_code == 200
    assert response.json()["members"] == ["kueche", "schlafzimmer"]
    assert (await client.get("/api/groups")).json()["groups"][0]["name"] == "OG"
    assert len(frames) == 2


async def test_put_unknown_group_is_404(client) -> None:
    response = await client.put("/api/groups/g_nope", json={"name": "A", "members": ["kueche"]})
    assert response.status_code == 404
    assert response.json()["error"] == "unknown_group"
    assert response.json()["message"] == "Diese Gruppe gibt es nicht."


async def test_put_onto_another_name_is_409(client) -> None:
    await make(client, "Oben", "schlafzimmer")
    other = await make(client, "Unten", "kueche")
    response = await client.put(
        f"/api/groups/{other['id']}", json={"name": "oben", "members": ["kueche"]}
    )
    assert response.status_code == 409


async def test_delete(client, frames) -> None:
    made = await make(client, "A", "kueche")
    assert (await client.delete(f"/api/groups/{made['id']}")).status_code == 204
    assert (await client.get("/api/groups")).json() == {"groups": []}
    assert frames[-1]["groups"] == []
    response = await client.delete(f"/api/groups/{made['id']}")
    assert response.status_code == 404
    assert response.json()["error"] == "unknown_group"


async def test_delete_leaves_shutters_and_other_groups_alone(client) -> None:
    a = await make(client, "A", "wohnzimmer", "kueche")
    b = await make(client, "B", "wohnzimmer")
    await client.delete(f"/api/groups/{a['id']}")
    assert (await client.get("/api/groups")).json()["groups"] == [
        {"id": b["id"], "name": "B", "members": ["wohnzimmer"]}
    ]
    assert len((await client.get("/api/shutters")).json()["shutters"]) == 3


async def test_order(client, frames) -> None:
    a = await make(client, "A", "kueche")
    b = await make(client, "B", "kueche")
    response = await client.put("/api/groups/order", json={"ids": [b["id"], a["id"]]})
    assert response.status_code == 200
    assert [g["name"] for g in response.json()["groups"]] == ["B", "A"]
    assert [g["name"] for g in frames[-1]["groups"]] == ["B", "A"]


async def test_order_must_name_every_group_once(client) -> None:
    a = await make(client, "A", "kueche")
    await make(client, "B", "kueche")
    response = await client.put("/api/groups/order", json={"ids": [a["id"]]})
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_order"


# --- US3: commanding a group --------------------------------------------------


async def test_command_reaches_every_member(client) -> None:
    group = await make(client, "Oben", "schlafzimmer", "wohnzimmer")
    response = await client.post(f"/api/groups/{group['id']}/command", json={"action": "close"})
    assert response.status_code == 200
    results = response.json()["results"]
    # configuration order, not member order (research §4)
    assert [r["id"] for r in results] == ["wohnzimmer", "schlafzimmer"]
    assert all(r["accepted"] and r["movement"]["target_percent"] == 0 for r in results)


async def test_command_partial_is_207(client) -> None:
    group = await make(client, "Unten", "wohnzimmer", "kueche")
    client.app.state.runs.is_measuring = lambda sid: sid == "kueche"  # type: ignore[method-assign]
    response = await client.post(f"/api/groups/{group['id']}/command", json={"action": "open"})
    assert response.status_code == 207
    by_id = {r["id"]: r for r in response.json()["results"]}
    assert by_id["kueche"] == {
        "id": "kueche",
        "accepted": False,
        "error": "measurement_in_progress",
    }
    assert by_id["wohnzimmer"]["accepted"] is True


async def test_command_with_bridge_down_is_503(client) -> None:
    group = await make(client, "Unten", "wohnzimmer", "kueche")
    await client.post("/api/sim/bridge/offline")
    response = await client.post(f"/api/groups/{group['id']}/command", json={"action": "close"})
    assert response.status_code == 503
    assert {r["error"] for r in response.json()["results"]} == {"bridge_unreachable"}


async def test_command_empty_group_is_409(client) -> None:
    group = await make(client, "Leer", "kueche")
    client.app.state.groups.prune(["wohnzimmer"])
    response = await client.post(f"/api/groups/{group['id']}/command", json={"action": "open"})
    assert response.status_code == 409
    assert response.json()["error"] == "empty_group"


async def test_command_unknown_group_is_404(client) -> None:
    response = await client.post("/api/groups/g_nope/command", json={"action": "open"})
    assert response.status_code == 404
    assert response.json()["error"] == "unknown_group"


async def test_command_position_needs_a_target(client) -> None:
    group = await make(client, "A", "kueche")
    response = await client.post(f"/api/groups/{group['id']}/command", json={"action": "position"})
    assert response.status_code == 422
    assert response.json()["error"] == "target_required"


async def test_command_position_and_stop(client) -> None:
    group = await make(client, "A", "kueche", "wohnzimmer")
    url = f"/api/groups/{group['id']}/command"
    moved = (await client.post(url, json={"action": "position", "target_percent": 30})).json()
    assert all(r["movement"]["target_percent"] == 30 for r in moved["results"])
    stopped = (await client.post(url, json={"action": "stop"})).json()
    assert all(r["accepted"] and r["movement"] is None for r in stopped["results"])
