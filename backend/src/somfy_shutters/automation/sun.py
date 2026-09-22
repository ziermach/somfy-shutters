"""Sunrise and sunset, computed on the Pi (constitution IV, FR-015).

The standard definition published tables use: the sun's centre 0.833 degrees below
the horizon (34' refraction plus 16' radius). astral's own `sunrise()` and
`sunset()` leave the refraction out, which makes every day about five minutes too
short at German latitudes; checked against published times, that failed FR-018's
two minutes. So the elevation is given explicitly.
"""

from __future__ import annotations

from datetime import date, datetime, tzinfo

from astral import Observer
from astral.sun import SunDirection, time_at_elevation

from .planner import SunLookup

HORIZON_ELEVATION = -0.833

_DIRECTION = {"sunrise": SunDirection.RISING, "sunset": SunDirection.SETTING}


def sun_lookup(latitude: float, longitude: float, tz: tzinfo) -> SunLookup:
    observer = Observer(latitude=latitude, longitude=longitude)

    def lookup(day: date, event: str) -> datetime | None:
        try:
            at = time_at_elevation(
                observer, HORIZON_ELEVATION, day, direction=_DIRECTION[event], tzinfo=tz
            )
        except ValueError:
            # astral raises when the sun never reaches that elevation that day.
            return None
        # astral can answer with the event of a neighbouring day near the poles.
        return at if at.date() == day else None

    return lookup
