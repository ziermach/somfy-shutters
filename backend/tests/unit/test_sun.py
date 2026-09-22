"""T025: sun times computed on the Pi agree with published ones to within 2 minutes (FR-018)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from somfy_shutters.automation.sun import sun_lookup

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "sun_berlin.json").read_text())
BERLIN = ZoneInfo("Europe/Berlin")
LOOKUP = sun_lookup(FIXTURE["latitude"], FIXTURE["longitude"], BERLIN)
CASES = [(d, e, t) for d, times in FIXTURE["days"].items() for e, t in times.items()]


@pytest.mark.parametrize(("day", "event", "published"), CASES)
def test_within_two_minutes_of_published_times(day: str, event: str, published: str) -> None:
    got = LOOKUP(date.fromisoformat(day), event)
    assert got is not None
    assert abs(got - datetime.fromisoformat(published)) <= timedelta(minutes=2)


def test_a_day_without_sunset_is_none_not_an_error() -> None:
    svalbard = sun_lookup(78.22, 15.65, ZoneInfo("Arctic/Longyearbyen"))
    assert svalbard(date(2026, 6, 21), "sunset") is None
