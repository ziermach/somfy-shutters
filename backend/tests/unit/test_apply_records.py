"""T034: commands.apply records who asked — after sending, and never in the way."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from somfy_shutters import commands
from somfy_shutters.auth.audit import AuditLog
from somfy_shutters.auth.models import Actor
from somfy_shutters.bridge.sim import SimBridge

ANNA = Actor("credential", "c_anna", "Anna")


class Runs:
    def __init__(self, *measuring: str) -> None:
        self.measuring = set(measuring)

    def is_measuring(self, shutter_id: str) -> bool:
        return shutter_id in self.measuring


class WatchedBridge(SimBridge):
    """Notes how many record entries existed at the moment each frame was sent."""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.entries_at_send: list[int] = []
        self.audit: AuditLog | None = None

    async def send_level(self, address: str, percent: int) -> None:
        assert self.audit is not None
        self.entries_at_send.append(len(self.audit.query()))
        await super().send_level(address, percent)


@pytest.fixture
def state(tracker, settings, tmp_path):
    bridge = WatchedBridge(addresses=[s.address for s in settings.shutter])
    audit = AuditLog(tmp_path / "audit.db")
    bridge.audit = audit
    yield SimpleNamespace(
        tracker=tracker, bridge=bridge, runs=Runs(), pending_checks={}, audit=audit
    )
    audit.close()


async def test_recorded_after_the_frame_went_out(state) -> None:
    await commands.apply(state, "wohnzimmer", "position", 30, ANNA)
    assert state.bridge.entries_at_send == [0]
    [entry] = state.audit.query()
    assert (entry.actor, entry.action, entry.outcome) == (ANNA, "command", "accepted")
    assert entry.shutter_id == "wohnzimmer" and entry.detail == {
        "action": "position",
        "percent": 30,
    }


async def test_a_ledger_that_cannot_be_written_does_not_stop_the_shutter(state, settings) -> None:
    state.bridge = SimBridge(addresses=[s.address for s in settings.shutter])
    state.audit.close()
    done = await commands.apply(state, "wohnzimmer", "close", actor=ANNA)
    assert done["accepted"] is True and done["movement"]["target_percent"] == 0


async def test_skipped_and_failed_are_recorded_too(state) -> None:
    state.runs = Runs("kueche")
    with pytest.raises(commands.MeasurementInProgress):
        await commands.apply(state, "kueche", "open", actor=ANNA)
    state.bridge.set_connected(False)
    results = await commands.apply_many(state, ["wohnzimmer"], "open", actor=ANNA)
    assert results[0]["error"] == "bridge_unreachable"
    assert [e.outcome for e in state.audit.query()] == ["failed", "skipped"]


async def test_no_ledger_no_record(tracker, settings) -> None:
    bare = SimpleNamespace(
        tracker=tracker,
        bridge=SimBridge(addresses=[s.address for s in settings.shutter]),
        runs=Runs(),
        pending_checks={},
    )
    assert (await commands.apply(bare, "wohnzimmer", "close"))["accepted"] is True
