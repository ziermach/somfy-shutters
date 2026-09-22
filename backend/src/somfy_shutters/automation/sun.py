"""Sunrise and sunset, computed on the Pi (constitution IV, FR-015).

astral's defaults use the standard -0.833° depression (refraction plus the sun's
radius), the definition published tables use.
"""

from __future__ import annotations

from datetime import date, datetime, tzinfo

from astral import Observer
from astral.sun import sunrise, sunset

from .planner import SunLookup


def sun_lookup(latitude: float, longitude: float, tz: tzinfo) -> SunLookup:
    observer = Observer(latitude=latitude, longitude=longitude)

    def lookup(day: date, event: str) -> datetime | None:
        compute = sunrise if event == "sunrise" else sunset
        try:
            return compute(observer, day, tzinfo=tz)
        except ValueError:
            # astral raises when the sun never reaches the horizon that day.
            return None

    return lookup
