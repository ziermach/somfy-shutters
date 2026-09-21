"""T009: a bare number must be unrepresentable.

Constitution principle III says an estimate is never shown as a reading. The
cheapest place to enforce that is the type, not every screen.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from somfy_shutters.models import Confidence, PositionEstimate, Source


def test_percent_requires_confidence() -> None:
    with pytest.raises(ValidationError):
        PositionEstimate(percent=62, source=Source.COMMAND)  # type: ignore[call-arg]


def test_unknown_must_not_carry_a_percentage() -> None:
    with pytest.raises(ValidationError, match="must not carry a percentage"):
        PositionEstimate(percent=62, confidence=Confidence.UNKNOWN, source=Source.RESTORED)


def test_known_confidence_requires_a_percentage() -> None:
    with pytest.raises(ValidationError, match="only be null when confidence is 'unknown'"):
        PositionEstimate(percent=None, confidence=Confidence.ESTIMATED, source=Source.COMMAND)


def test_certain_requires_a_timestamp() -> None:
    with pytest.raises(ValidationError, match="record when it became certain"):
        PositionEstimate(percent=100, confidence=Confidence.CERTAIN, source=Source.COMMAND)


def test_only_end_stops_can_be_certain() -> None:
    with pytest.raises(ValueError, match="only 0 and 100 are end stops"):
        PositionEstimate.at_end_stop(62, Source.COMMAND)


def test_serialised_position_always_carries_confidence() -> None:
    position = PositionEstimate.at_end_stop(100, Source.COMMAND)
    assert set(position.model_dump()) >= {"percent", "confidence"}
    assert position.model_dump()["confidence"] == "certain"


def test_stale_is_derived_not_stored(clock) -> None:
    fresh = PositionEstimate(
        percent=62,
        confidence=Confidence.ESTIMATED,
        certain_at=clock.now(),
        source=Source.COMMAND,
    )
    assert fresh.is_stale(12, clock.now()) is False
    clock.advance(13 * 3600)
    assert fresh.is_stale(12, clock.now()) is True
    assert "stale" not in fresh.model_dump()


def test_certain_is_never_stale(clock) -> None:
    """An end stop does not rot: the shutter is still mechanically there."""
    position = PositionEstimate.at_end_stop(0, Source.COMMAND, clock.now())
    clock.advance(365 * 24 * 3600)
    assert position.is_stale(12, clock.now()) is False
