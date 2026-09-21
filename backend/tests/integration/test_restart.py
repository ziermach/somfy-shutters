"""T036: FR-010, what survives a restart and what must not."""

from __future__ import annotations

import pytest

from somfy_shutters.config import Settings
from somfy_shutters.models import Confidence, Source
from somfy_shutters.store import Store
from somfy_shutters.tracker import Tracker

from ..conftest import CONFIG, FakeClock


def build(store: Store, clock: FakeClock) -> Tracker:
    async def emit(event: dict) -> None:
        return None

    return Tracker(
        Settings.model_validate(CONFIG),
        store,
        emit=emit,
        monotonic=clock.monotonic,
        clock=clock.now,
    )


@pytest.fixture
def db(tmp_path):
    return tmp_path / "state.db"


async def test_a_shutter_at_an_end_stop_survives(db) -> None:
    clock = FakeClock()
    store = Store(db)
    tracker = build(store, clock)
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.0)
    await tracker.tick()
    store.close()

    store = Store(db)
    revived = build(store, clock)
    position = revived.position("wohnzimmer")
    store.close()

    assert position.percent == 100
    assert position.confidence is Confidence.CERTAIN


async def test_an_estimate_survives_with_its_age(db) -> None:
    clock = FakeClock()
    store = Store(db)
    tracker = build(store, clock)
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.0)
    await tracker.tick()
    certain_at = tracker.position("wohnzimmer").certain_at
    await tracker._settle("wohnzimmer", 62, Source.COMMAND)
    store.close()

    store = Store(db)
    revived = build(store, clock)
    position = revived.position("wohnzimmer")
    store.close()

    assert position.percent == 62
    assert position.confidence is Confidence.ESTIMATED
    assert position.certain_at == certain_at, "the age of the last certainty must survive"


async def test_a_shutter_interrupted_mid_travel_comes_back_unknown(db) -> None:
    """The heart of FR-010: not the value it left, not the one it was heading for."""
    clock = FakeClock()
    store = Store(db)
    tracker = build(store, clock)
    await tracker.start_movement("wohnzimmer", 100)
    clock.advance(18.0)
    await tracker.tick()
    await tracker.start_movement("wohnzimmer", 0)
    clock.advance(6.0)
    store.close()  # the power goes out here

    store = Store(db)
    revived = build(store, clock)
    position = revived.position("wohnzimmer")
    store.close()

    assert position.confidence is Confidence.UNKNOWN
    assert position.percent is None


async def test_a_shutter_never_seen_before_is_unknown(db) -> None:
    store = Store(db)
    tracker = build(store, FakeClock())
    assert tracker.position("schlafzimmer").confidence is Confidence.UNKNOWN
    store.close()
