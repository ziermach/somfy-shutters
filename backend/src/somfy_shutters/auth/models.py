"""Who is asking, and what they may do (specs/007-api-auth-audit/data-model.md)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_NAME = 40


class Ability(StrEnum):
    WATCH = "watch"
    COMMAND = "command"
    CONFIGURE = "configure"
    CALIBRATE = "calibrate"
    MANAGE = "manage"


ALL_ABILITIES = frozenset(Ability)


def with_watch(abilities: set[Ability] | frozenset[Ability]) -> frozenset[Ability]:
    """Every ability implies watching: whoever may close a shutter may see it."""
    return frozenset(abilities) | {Ability.WATCH}


def ordered(abilities: frozenset[Ability]) -> list[str]:
    return [a.value for a in Ability if a in abilities]


class CredentialDraft(BaseModel):
    """What the owner asks for when issuing (POST /api/auth/credentials)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    abilities: list[Ability] = Field(min_length=1)
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        if len(value) > MAX_NAME:
            raise ValueError(f"name must be at most {MAX_NAME} characters")
        return value


@dataclass(frozen=True)
class Credential:
    id: str
    name: str
    abilities: frozenset[Ability]
    origin: str  # issued | paired | recovery
    created_by: str | None
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None

    def state(self, now: datetime) -> str:
        if self.revoked_at is not None:
            return "revoked"
        if self.expires_at is not None and self.expires_at <= now:
            return "expired"
        return "active"


@dataclass(frozen=True)
class PairingCode:
    id: str
    abilities: frozenset[Ability]
    minted_by: str | None
    created_at: datetime
    expires_at: datetime
    spent_at: datetime | None
    cancelled_at: datetime | None
    credential_id: str | None

    def outstanding(self, now: datetime) -> bool:
        return self.spent_at is None and self.cancelled_at is None and self.expires_at > now


@dataclass(frozen=True)
class Actor:
    """Who a record entry is about. The name is kept as it was, so an entry still
    reads "Anna" after Anna's phone was revoked (FR-017)."""

    kind: str  # credential | automation | bridge | recovery | simulator | anonymous | system
    id: str | None = None
    name: str | None = None


SYSTEM = Actor("system")
ANONYMOUS = Actor("anonymous")
BRIDGE = Actor("bridge", name="Funkbrücke")
RECOVERY = Actor("recovery", name="Wiederherstellung")


@dataclass(frozen=True)
class Caller:
    """The identity a request resolved to."""

    actor: Actor
    abilities: frozenset[Ability]
    credential_id: str | None = None
    via: str | None = None  # bearer | cookie | None (open mode)

    def can(self, ability: Ability) -> bool:
        return ability in self.abilities


SIMULATOR = Caller(Actor("simulator", name="Simulator"), ALL_ABILITIES)
"""Open mode (research §10): every request acts as this, so the record still has an actor."""
