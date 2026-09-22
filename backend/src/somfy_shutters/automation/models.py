"""Rules, triggers, actions and firing records (specs/003-shutter-automations/data-model.md)."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_OFFSET_MINUTES = 360


def _hhmm(value: str | None) -> str | None:
    if value is not None and not HHMM.match(value):
        raise ValueError(f"expected HH:MM, got {value!r}")
    return value


class TimeTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["time"] = "time"
    time: str

    @field_validator("time")
    @classmethod
    def _check_time(cls, value: str) -> str:
        return _hhmm(value)  # type: ignore[return-value]


class SunTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["sunrise", "sunset"]
    offset_minutes: int = Field(default=0, ge=-MAX_OFFSET_MINUTES, le=MAX_OFFSET_MINUTES)
    not_before: str | None = None
    not_after: str | None = None

    @field_validator("not_before", "not_after")
    @classmethod
    def _check_bounds(cls, value: str | None) -> str | None:
        return _hhmm(value)

    @model_validator(mode="after")
    def _ordered(self) -> SunTrigger:
        if self.not_before and self.not_after and self.not_before >= self.not_after:
            raise ValueError("not_before must be earlier than not_after")
        return self


Trigger = Annotated[TimeTrigger | SunTrigger, Field(discriminator="kind")]


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["open", "close", "position"]
    percent: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _percent_only_for_position(self) -> Action:
        if self.kind == "position" and self.percent is None:
            raise ValueError("a position action needs percent")
        if self.kind != "position" and self.percent is not None:
            raise ValueError("percent is only for a position action")
        return self

    def same_effect(self, other: Action) -> bool:
        return self.kind == other.kind and self.percent == other.percent


class RuleDraft(BaseModel):
    """What a person edits. Everything a rule is, minus identity and bookkeeping."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    enabled: bool = True
    days: list[bool] = Field(min_length=7, max_length=7)
    """Monday first. All false is allowed: the rule then never fires, and says so."""
    trigger: Trigger
    targets: Literal["all"] | list[str]
    action: Action

    @field_validator("name")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("targets")
    @classmethod
    def _non_empty(cls, value: Literal["all"] | list[str]) -> Literal["all"] | list[str]:
        if isinstance(value, list):
            if not value:
                raise ValueError("choose at least one shutter, or all")
            if len(set(value)) != len(value):
                raise ValueError("a shutter is listed twice")
        return value

    @property
    def is_sun(self) -> bool:
        return self.trigger.kind != "time"


class Rule(RuleDraft):
    id: str
    skip_planned_at: datetime | None = None
    """UTC instant of the one firing to skip (FR-025)."""
    created_at: datetime
    updated_at: datetime


class FiringStatus(StrEnum):
    FIRED = "fired"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"
    PAUSED = "paused"
    HELD = "held"
    MISSED = "missed"
    NO_SUN = "no_sun"


class Outcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    shutter_id: str
    result: Literal["commanded", "skipped", "failed"]
    reason: Literal["measurement_in_progress", "removed", "bridge_unreachable"] | None = None


class Firing(BaseModel):
    rule_id: str
    planned_at: datetime
    fired_at: datetime | None = None
    status: FiringStatus
    outcomes: list[Outcome] = Field(default_factory=list)

    @property
    def commanded(self) -> int:
        return sum(1 for o in self.outcomes if o.result == "commanded")


def status_from(outcomes: list[Outcome]) -> FiringStatus:
    """What a firing that sent commands amounts to."""
    commanded = sum(1 for o in outcomes if o.result == "commanded")
    if outcomes and commanded == len(outcomes):
        return FiringStatus.FIRED
    if commanded:
        return FiringStatus.PARTIAL
    return FiringStatus.FAILED
