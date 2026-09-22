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


class Targets(BaseModel):
    """Individual shutters and groups (feature 004). Groups are resolved when the
    rule fires, so a shutter added to a group is included without editing the rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    shutters: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)

    @field_validator("shutters", "groups")
    @classmethod
    def _a_set(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("listed twice")
        return value

    @property
    def empty(self) -> bool:
        return not self.shutters and not self.groups

    def wire(self) -> dict[str, list[str]]:
        return {"shutters": list(self.shutters), "groups": list(self.groups)}


RuleTargets = Literal["all"] | Targets


def targets_wire(targets: RuleTargets) -> str | dict[str, list[str]]:
    return targets if targets == "all" else targets.wire()  # type: ignore[union-attr]


class RuleDraft(BaseModel):
    """What a person edits. Everything a rule is, minus identity and bookkeeping."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    enabled: bool = True
    days: list[bool] = Field(min_length=7, max_length=7)
    """Monday first. All false is allowed: the rule then never fires, and says so."""
    trigger: Trigger
    targets: RuleTargets
    action: Action

    @field_validator("name")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("targets", mode="before")
    @classmethod
    def _plain_list_is_shutters(cls, value: object) -> object:
        """Feature 003 wrote, and older clients still send, a plain list of shutters."""
        if isinstance(value, list):
            return {"shutters": value, "groups": []}
        return value

    @model_validator(mode="after")
    def _names_a_target(self) -> RuleDraft:
        if self.targets != "all" and self.targets.empty:  # type: ignore[union-attr]
            raise ValueError("choose at least one shutter or group, or all")
        return self

    @property
    def is_sun(self) -> bool:
        return self.trigger.kind != "time"


class Rule(RuleDraft):
    id: str
    skip_planned_at: datetime | None = None
    """UTC instant of the one firing to skip (FR-025)."""
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _names_a_target(self) -> Rule:
        """Replaces the draft's check of the same name. A stored rule may have lost
        its last target to a deleted group (feature 004, FR-026); it then says
        "no_targets" and does not fire, rather than failing to load."""
        return self


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
    via: list[str] = Field(default_factory=list)
    """Names of the groups this shutter was reached through, at firing time (feature
    004, FR-027). Empty for a direct target or "all", and in rows from before 004."""


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
