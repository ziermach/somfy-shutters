"""T003: one loop for "Alle", groups and automations (feature 004, research §3)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from somfy_shutters import commands
from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.tracker import Tracker

IDS = ["wohnzimmer", "kueche", "schlafzimmer"]


class Runs:
    def __init__(self, *measuring: str) -> None:
        self.measuring = set(measuring)

    def is_measuring(self, shutter_id: str) -> bool:
        return shutter_id in self.measuring


class RecordingBridge(SimBridge):
    """The simulator, noting every address it was asked to move, in order."""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.sent: list[str] = []

    async def send_level(self, address: str, percent: int) -> None:
        await super().send_level(address, percent)
        self.sent.append(address)


@pytest.fixture
def state(tracker: Tracker, settings) -> SimpleNamespace:
    bridge = RecordingBridge(addresses=[s.address for s in settings.shutter])
    return SimpleNamespace(tracker=tracker, bridge=bridge, runs=Runs(), pending_checks={})


def address(state, shutter_id: str) -> str:
    return state.tracker.settings.shutters[shutter_id].address


async def test_all_accepted_carry_their_movement(state) -> None:
    results = await commands.apply_many(state, IDS, "close")
    assert [r["id"] for r in results] == IDS
    assert all(r["accepted"] for r in results)
    assert all(r["movement"]["target_percent"] == 0 for r in results)


async def test_one_being_measured_does_not_stop_the_others(state) -> None:
    state.runs = Runs("kueche")
    results = await commands.apply_many(state, IDS, "open")
    by_id = {r["id"]: r for r in results}
    assert by_id["kueche"] == {"id": "kueche", "accepted": False, "error": "measurement_in_progress"}
    assert by_id["wohnzimmer"]["accepted"] and by_id["schlafzimmer"]["accepted"]
    assert address(state, "kueche") not in state.bridge.sent


async def test_bridge_offline_reports_every_one_and_queues_nothing(state) -> None:
    state.bridge.set_connected(False)
    results = await commands.apply_many(state, IDS, "close")
    assert all(r == {"id": r["id"], "accepted": False, "error": "bridge_unreachable"} for r in results)
    state.bridge.set_connected(True)
    assert state.bridge.sent == []
    assert all(state.tracker.movement(sid) is None for sid in IDS)


async def test_stop_returns_no_movement(state) -> None:
    await commands.apply_many(state, IDS, "close")
    results = await commands.apply_many(state, IDS, "stop")
    assert all(r["accepted"] and r["movement"] is None for r in results)


async def test_commands_go_out_in_the_order_given(state) -> None:
    order = ["schlafzimmer", "wohnzimmer", "kueche"]
    await commands.apply_many(state, order, "close")
    assert state.bridge.sent == [address(state, sid) for sid in order]


async def test_position_reaches_every_one(state) -> None:
    results = await commands.apply_many(state, IDS, "position", 30)
    assert all(r["movement"]["target_percent"] == 30 for r in results)
