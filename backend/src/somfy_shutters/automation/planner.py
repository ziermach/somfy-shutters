"""When a rule fires. Pure: no clock, no I/O, no scheduler.

Everything the engine does rests on these answers, so they are computed here and
nowhere else — the list's "next firing", the form's "heute 19:12", the engine's
wake-up time and the catch-up after a restart all call the same functions.

Semantics (specs/003-shutter-automations/research.md §2):

- A rule belongs to a local calendar date, its **base date**; the weekday selection
  applies to that date. The firing itself may fall on the next day (sunset + 5 h).
- A wall time that does not exist (spring forward) fires at the first minute after
  it that does. One that exists twice (fall back) fires at the first occurrence only.
- A sun time is the event plus the offset, moved into [not_before, not_after].
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from .models import RuleDraft, SunTrigger

SEARCH_DAYS_AHEAD = 8

SunLookup = Callable[[date, str], datetime | None]
"""(base date, "sunrise" | "sunset") -> the event as an aware datetime, or None when
the sun does not rise or set that day. None as a whole means no location is set."""


@dataclass(frozen=True)
class NextFiring:
    at: datetime | None
    reason: str | None = None
    """Why there is none: disabled, no_days, no_targets, no_location."""


def _parse(hhmm: str) -> time:
    hours, minutes = hhmm.split(":")
    return time(int(hours), int(minutes))


def wall_clock(day: date, at: time, tz: tzinfo) -> datetime:
    """A local wall time on `day` as an aware instant, by the DST rules above."""
    naive = datetime.combine(day, at)
    candidate = naive.replace(tzinfo=tz, fold=0)
    # A time in the spring-forward gap does not survive a round trip through UTC.
    for _ in range(24 * 60):
        if candidate.astimezone(UTC).astimezone(tz).replace(tzinfo=None) == naive:
            return candidate
        naive += timedelta(minutes=1)
        candidate = naive.replace(tzinfo=tz, fold=0)
    raise ValueError(f"no valid local time near {day} {at} in {tz}")


def firing_on(rule: RuleDraft, day: date, tz: tzinfo, sun: SunLookup | None) -> datetime | None:
    """The instant the rule fires for base date `day`, ignoring weekday selection.

    None when a sun event does not happen that day (or no location is known).
    """
    trigger = rule.trigger
    if not isinstance(trigger, SunTrigger):
        return wall_clock(day, _parse(trigger.time), tz)
    if sun is None:
        return None
    event = sun(day, trigger.kind)
    if event is None:
        return None
    at = event.astimezone(tz) + timedelta(minutes=trigger.offset_minutes)
    if trigger.not_before is not None:
        earliest = wall_clock(day, _parse(trigger.not_before), tz)
        at = max(at, earliest)
    if trigger.not_after is not None:
        latest = wall_clock(day, _parse(trigger.not_after), tz)
        at = min(at, latest)
    # Whole minutes: a firing is shown and deduplicated at minute precision.
    return at.replace(second=0, microsecond=0)


def _selected(rule: RuleDraft, day: date) -> bool:
    return rule.days[day.weekday()]


def _candidates(
    rule: RuleDraft, first_day: date, last_day: date, tz: tzinfo, sun: SunLookup | None
) -> Iterator[tuple[date, datetime]]:
    day = first_day
    while day <= last_day:
        if _selected(rule, day):
            at = firing_on(rule, day, tz, sun)
            if at is not None:
                yield day, at
        day += timedelta(days=1)


def next_firing(
    rule: RuleDraft,
    after: datetime,
    tz: tzinfo,
    sun: SunLookup | None,
    *,
    has_targets: bool = True,
) -> NextFiring:
    """The first firing strictly after `after`, or why there is none."""
    if not rule.enabled:
        return NextFiring(None, "disabled")
    if not any(rule.days):
        return NextFiring(None, "no_days")
    if not has_targets:
        return NextFiring(None, "no_targets")
    if rule.is_sun and sun is None:
        return NextFiring(None, "no_location")
    local = after.astimezone(tz).date()
    # From the day before: a firing that belongs to yesterday can land after midnight.
    for _day, at in _candidates(
        rule, local - timedelta(days=1), local + timedelta(days=SEARCH_DAYS_AHEAD), tz, sun
    ):
        if at > after:
            return NextFiring(at)
    # Only possible for a sun rule on days without the event.
    return NextFiring(None, "no_sun")


def firings_between(
    rule: RuleDraft, start: datetime, end: datetime, tz: tzinfo, sun: SunLookup | None
) -> list[datetime]:
    """Every firing in (start, end], in order. For catch-up and the conflict check."""
    if not any(rule.days) or (rule.is_sun and sun is None):
        return []
    first = start.astimezone(tz).date() - timedelta(days=1)
    last = end.astimezone(tz).date()
    return sorted(at for _day, at in _candidates(rule, first, last, tz, sun) if start < at <= end)


def days_without_sun(
    rule: RuleDraft, start: datetime, end: datetime, tz: tzinfo, sun: SunLookup | None
) -> list[date]:
    """Selected base dates in the window whose sun event does not happen."""
    if not rule.is_sun or sun is None:
        return []
    out = []
    day = start.astimezone(tz).date()
    while day <= end.astimezone(tz).date():
        if _selected(rule, day) and firing_on(rule, day, tz, sun) is None:
            out.append(day)
        day += timedelta(days=1)
    return out


def today_at(rule: RuleDraft, now: datetime, tz: tzinfo, sun: SunLookup | None) -> datetime | None:
    """What the trigger resolves to today, selected day or not — for "heute 19:12"."""
    return firing_on(rule, now.astimezone(tz).date(), tz, sun)
