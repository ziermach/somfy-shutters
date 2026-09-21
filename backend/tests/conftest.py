from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from somfy_shutters.config import Settings
from somfy_shutters.store import Store
from somfy_shutters.tracker import Tracker

CONFIG = {
    "general": {"stale_after_hours": 12, "default_travel_seconds": 20},
    "bridge": {"kind": "sim", "invert_level": False},
    "shutter": [
        {
            "id": "wohnzimmer",
            "name": "Wohnzimmer",
            "address": "0x279621",
            "travel_up_seconds": 18.0,
            "travel_down_seconds": 16.0,
        },
        {"id": "kueche", "name": "Küche", "address": "0x279622", "travel_up_seconds": 12.0},
        {"id": "schlafzimmer", "name": "Schlafzimmer", "address": "0x279623"},
    ],
}


class FakeClock:
    """Time under test control — no sleeping, no flakiness."""

    def __init__(self) -> None:
        self.mono = 1000.0
        self.wall = datetime(2026, 9, 21, 18, 0, 0, tzinfo=UTC)

    def advance(self, seconds: float) -> None:
        self.mono += seconds
        self.wall += timedelta(seconds=seconds)

    def monotonic(self) -> float:
        return self.mono

    def now(self) -> datetime:
        return self.wall


@pytest.fixture
def settings() -> Settings:
    return Settings.model_validate(CONFIG)


@pytest.fixture
def store(tmp_path) -> Iterator[Store]:
    store = Store(tmp_path / "state.db")
    yield store
    store.close()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def events() -> list[dict]:
    return []


@pytest.fixture
def tracker(settings: Settings, store: Store, clock: FakeClock, events: list[dict]) -> Tracker:
    async def emit(event: dict) -> None:
        events.append(event)

    return Tracker(
        settings,
        store,
        emit=emit,
        monotonic=clock.monotonic,
        clock=clock.now,
    )


@pytest.fixture
def seq() -> Iterator[int]:
    return itertools.count(1)
