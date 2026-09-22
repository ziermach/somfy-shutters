"""When a rule fires: weekdays, daylight saving, and the edges of a search window.

Pure arithmetic, so every rule the spec states about firing times is asserted
here rather than discovered on a winter morning.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from somfy_shutters.automation.models import RuleDraft
from somfy_shutters.automation.planner import firings_between, next_firing, wall_clock

BERLIN = ZoneInfo("Europe/Berlin")
WEEKDAYS = [True] * 5 + [False] * 2
EVERY_DAY = [True] * 7


def rule(time: str = "06:45", days: list[bool] = WEEKDAYS, **over) -> RuleDraft:
    body = {
        "name": "Test",
        "days": days,
        "trigger": {"kind": "time", "time": time},
        "targets": "all",
        "action": {"kind": "open"},
    }
    body.update(over)
    return RuleDraft.model_validate(body)


def local(*args: int) -> datetime:
    return datetime(*args, tzinfo=BERLIN)


def test_fires_later_today_on_a_selected_day() -> None:
    # 2026-09-22 is a Tuesday
    got = next_firing(rule(), local(2026, 9, 22, 6, 0), BERLIN, None)
    assert got.at == local(2026, 9, 22, 6, 45)


def test_a_firing_exactly_at_after_is_not_the_next_one() -> None:
    got = next_firing(rule(), local(2026, 9, 22, 6, 45), BERLIN, None)
    assert got.at == local(2026, 9, 23, 6, 45)


def test_skips_the_weekend() -> None:
    # Friday evening -> Monday morning
    got = next_firing(rule(), local(2026, 9, 25, 20, 0), BERLIN, None)
    assert got.at == local(2026, 9, 28, 6, 45)


def test_no_days_selected_never_fires_and_says_so() -> None:
    got = next_firing(rule(days=[False] * 7), local(2026, 9, 22, 6, 0), BERLIN, None)
    assert got.at is None and got.reason == "no_days"


def test_a_disabled_rule_says_so() -> None:
    got = next_firing(rule(enabled=False), local(2026, 9, 22, 6, 0), BERLIN, None)
    assert got.reason == "disabled"


def test_no_targets_left_says_so() -> None:
    got = next_firing(rule(), local(2026, 9, 22, 6, 0), BERLIN, None, has_targets=False)
    assert got.reason == "no_targets"


def test_spring_forward_gap_fires_at_the_first_valid_minute() -> None:
    """2026-03-29: 02:00 jumps to 03:00 in Berlin. 02:30 does not exist."""
    got = next_firing(rule("02:30", EVERY_DAY), local(2026, 3, 29, 1, 0), BERLIN, None)
    assert got.at is not None
    assert got.at.astimezone(BERLIN).strftime("%H:%M") == "03:00"
    assert got.at.utcoffset() == timedelta(hours=2)


def test_fall_back_fires_once() -> None:
    """2026-10-25: 03:00 falls back to 02:00, so 02:30 happens twice. One firing."""
    start = local(2026, 10, 25, 0, 0)
    end = local(2026, 10, 25, 23, 0)
    got = firings_between(rule("02:30", EVERY_DAY), start, end, BERLIN, None)
    assert len(got) == 1
    assert got[0].utcoffset() == timedelta(hours=2), "the first occurrence, still summer time"


def test_the_day_after_fall_back_is_ordinary() -> None:
    got = next_firing(rule("02:30", EVERY_DAY), local(2026, 10, 25, 12, 0), BERLIN, None)
    assert got.at == local(2026, 10, 26, 2, 30)


def test_firings_between_lists_each_selected_day_once_in_order() -> None:
    start = local(2026, 9, 21, 0, 0)  # Monday
    got = firings_between(rule(), start, start + timedelta(days=7), BERLIN, None)
    assert [g.astimezone(BERLIN).day for g in got] == [21, 22, 23, 24, 25]


def test_firings_between_is_half_open() -> None:
    at = local(2026, 9, 22, 6, 45)
    assert firings_between(rule(), at, at + timedelta(hours=1), BERLIN, None) == []
    assert firings_between(rule(), at - timedelta(hours=1), at, BERLIN, None) == [at]


@pytest.mark.parametrize("hhmm", ["00:00", "02:30", "23:59"])
def test_wall_clock_round_trips_on_ordinary_days(hhmm: str) -> None:
    h, m = map(int, hhmm.split(":"))
    from datetime import date, time

    at = wall_clock(date(2026, 7, 1), time(h, m), BERLIN)
    assert at.astimezone(UTC).astimezone(BERLIN).strftime("%H:%M") == hhmm
