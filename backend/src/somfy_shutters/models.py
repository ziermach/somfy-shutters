"""Entities.

The point of this module is the invariant in :class:`PositionEstimate`: a position
cannot exist without saying how much it can be trusted. Constitution principle III
is a type error here, not a convention someone has to remember in the UI layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


class Confidence(StrEnum):
    CERTAIN = "certain"
    """At an end stop it just reached. The only thing the system actually knows."""

    ESTIMATED = "estimated"
    """Computed from travel time. Drifts, and says so."""

    UNKNOWN = "unknown"
    """No trustworthy basis — after a restart mid-travel, or never established."""


class Source(StrEnum):
    COMMAND = "command"
    REPORT = "report"
    RESTORED = "restored"


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"


class Origin(StrEnum):
    LOCAL = "local"
    """We issued the command."""

    EXTERNAL = "external"
    """Inferred from a report stream — somebody used a physical remote."""


class Action(StrEnum):
    OPEN = "open"
    CLOSE = "close"
    STOP = "stop"
    POSITION = "position"


class PositionEstimate(BaseModel):
    """A position and how much it can be trusted. Never one without the other."""

    model_config = ConfigDict(frozen=True)

    percent: int | None = Field(default=None, ge=0, le=100)
    confidence: Confidence
    certain_at: datetime | None = None
    source: Source

    @model_validator(mode="after")
    def _percent_matches_confidence(self) -> PositionEstimate:
        if self.confidence is Confidence.UNKNOWN:
            if self.percent is not None:
                raise ValueError("an unknown position must not carry a percentage")
        elif self.percent is None:
            raise ValueError("percent may only be null when confidence is 'unknown'")
        if self.confidence is Confidence.CERTAIN and self.certain_at is None:
            raise ValueError("a certain position must record when it became certain")
        return self

    def age_seconds(self, now: datetime | None = None) -> float | None:
        if self.certain_at is None:
            return None
        return ((now or utcnow()) - self.certain_at).total_seconds()

    def is_stale(self, stale_after_hours: float, now: datetime | None = None) -> bool:
        """Stale is not a fourth confidence — it is an estimate with an old clock."""
        if self.confidence is not Confidence.ESTIMATED:
            return False
        age = self.age_seconds(now)
        return age is None or age > stale_after_hours * 3600

    @classmethod
    def unknown(cls, source: Source = Source.RESTORED) -> PositionEstimate:
        return cls(percent=None, confidence=Confidence.UNKNOWN, source=source)

    @classmethod
    def at_end_stop(
        cls, percent: int, source: Source, when: datetime | None = None
    ) -> PositionEstimate:
        if percent not in (0, 100):
            raise ValueError("only 0 and 100 are end stops")
        return cls(
            percent=percent,
            confidence=Confidence.CERTAIN,
            certain_at=when or utcnow(),
            source=source,
        )


class Movement(BaseModel):
    """Travel in progress. Never persisted — a movement interrupted by a restart is
    exactly the case that has to come back as unknown (FR-010)."""

    model_config = ConfigDict(frozen=True)

    shutter_id: str
    from_percent: int = Field(ge=0, le=100)
    target_percent: int = Field(ge=0, le=100)
    direction: Direction
    started_at: datetime
    expected_arrival: datetime
    origin: Origin = Origin.LOCAL
    # Monotonic clock, so a daylight-saving jump mid-travel cannot distort the
    # animation. The wall-clock fields above are what clients render.
    started_monotonic: float
    duration_seconds: float

    def progress(self, now_monotonic: float) -> float:
        if self.duration_seconds <= 0:
            return 1.0
        return min(1.0, max(0.0, (now_monotonic - self.started_monotonic) / self.duration_seconds))

    def position_at(self, now_monotonic: float, curve_k: float = 0.0) -> int:
        span = self.target_percent - self.from_percent
        progress = self.progress(now_monotonic)
        if curve_k:
            from .calibration import travel_curve

            progress = travel_curve(progress, curve_k)
        return round(self.from_percent + span * progress)

    def is_done(self, now_monotonic: float) -> bool:
        return self.progress(now_monotonic) >= 1.0


class Command(BaseModel):
    model_config = ConfigDict(frozen=True)

    shutter_id: str
    action: Action
    target_percent: int | None = Field(default=None, ge=0, le=100)
    issued_at: datetime = Field(default_factory=utcnow)
    accepted: bool = False

    @model_validator(mode="after")
    def _position_needs_a_target(self) -> Command:
        if self.action is Action.POSITION and self.target_percent is None:
            raise ValueError("action 'position' requires target_percent")
        return self


class BridgeStatus(BaseModel):
    connected: bool
    kind: Literal["mqtt", "sim"]


class RunKind(StrEnum):
    GUIDED = "guided"
    """Two presses in the calibration wizard."""

    CONFIRMED = "confirmed"
    """One tap after an ordinary travel — the cheapest observation that exists."""


class CheckReply(StrEnum):
    TOO_HIGH = "too_high"
    ABOUT_RIGHT = "about_right"
    TOO_LOW = "too_low"


class MeasurementRun(BaseModel):
    """One observed travel. Rejected runs are kept, not discarded: the user is
    shown why a run did not count (FR-012)."""

    model_config = ConfigDict(frozen=True)

    shutter_id: str
    direction: Direction
    dead_seconds: float = Field(ge=0)
    total_seconds: float = Field(gt=0)
    recorded_at: datetime = Field(default_factory=utcnow)
    kind: RunKind = RunKind.GUIDED
    rejected: str | None = None
    id: int | None = None

    @property
    def counts(self) -> bool:
        return self.rejected is None


class Calibration(BaseModel):
    """What the system currently believes about one shutter and direction."""

    model_config = ConfigDict(frozen=True)

    travel_seconds: float = Field(ge=1, le=600)
    dead_seconds: float = Field(default=0.0, ge=0)
    runs: int = Field(default=0, ge=0)
    curve_k: float = Field(default=0.0, ge=-0.8, le=0.8)
    updated_at: datetime | None = None
    source: Literal["manual", "measured", "default"] = "default"


class CheckAnswer(BaseModel):
    """One verification response. Stored so the effect can be undone (FR-026)."""

    model_config = ConfigDict(frozen=True)

    shutter_id: str
    direction: Direction
    answer: CheckReply
    recorded_at: datetime = Field(default_factory=utcnow)
