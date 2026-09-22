"""Configuration: which shutters exist, and the physical values someone measured.

The constitution keeps measured values out of code, so travel times and addresses
live here. Validation is strict and startup fails loudly — a mistyped address is
otherwise completely silent, since the radio never answers.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ADDRESS_PATTERN = r"^0x[0-9a-f]{6}$"
ID_PATTERN = r"^[a-z0-9_-]+$"


class GeneralConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stale_after_hours: float = Field(default=12, gt=0)
    default_travel_seconds: float = Field(default=20, ge=1, le=600)
    timezone: str = "Europe/Berlin"
    """The wall clock automations follow (feature 003). Named explicitly rather
    than read from the OS, so a reinstall cannot move every rule by an hour."""

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone {value!r}") from exc
        return value

    @property
    def tz(self):  # zoneinfo.ZoneInfo, imported lazily
        from zoneinfo import ZoneInfo

        return ZoneInfo(self.timezone)


class LocationConfig(BaseModel):
    """Where the house is, for sunrise and sunset. Seeds the app once; after that
    the location set in the app wins."""

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class BridgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["mqtt", "sim"] = "sim"
    host: str = "localhost"
    port: int = Field(default=1883, ge=1, le=65535)
    user: str | None = None
    password: str | None = None
    invert_level: bool = False
    """Open hardware question 1. Flipping this must be sufficient on its own."""


class AuthConfig(BaseModel):
    """Who may talk to the backend (feature 007, specs/007-api-auth-audit/data-model.md).

    `mode` left out means: open with the simulator, required with anything else. The
    exemption is keyed to the one thing that makes it harmless — no radio — so it
    cannot be left switched on in front of real windows.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["required", "open"] | None = None
    failed_attempts: int = Field(default=10, ge=1)
    failed_window_minutes: float = Field(default=5, gt=0)
    lockout_minutes: float = Field(default=15, gt=0)
    command_burst: int = Field(default=10, ge=1)
    command_per_second: float = Field(default=1.0, gt=0)
    pairing_minutes: float = Field(default=5, gt=0, le=60)
    audit_retention_days: int = Field(default=180, ge=1)
    trusted_proxy: str | None = None
    """Only a request from this peer may name its client in X-Forwarded-For."""

    @property
    def required(self) -> bool:
        return self.mode != "open"


class ShutterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)
    address: str
    travel_up_seconds: float | None = Field(default=None, ge=1, le=600)
    travel_down_seconds: float | None = Field(default=None, ge=1, le=600)

    @field_validator("address")
    @classmethod
    def _address_shape(cls, value: str) -> str:
        import re

        lowered = value.strip().lower()
        if not re.match(ADDRESS_PATTERN, lowered):
            raise ValueError(f"address must look like 0x279621, got {value!r}")
        return lowered

    @property
    def calibrated(self) -> bool:
        return self.travel_up_seconds is not None and self.travel_down_seconds is not None


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    location: LocationConfig | None = None
    auth: AuthConfig = Field(default_factory=AuthConfig)
    shutter: list[ShutterConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _auth_mode(self) -> Settings:
        if self.auth.mode is None:
            self.auth.mode = "open" if self.bridge.kind == "sim" else "required"
        elif self.auth.mode == "open" and self.bridge.kind != "sim":
            # FR-029: a real installation always asks for a credential.
            raise ValueError('auth.mode = "open" ist nur mit dem Simulator erlaubt.')
        return self

    @model_validator(mode="after")
    def _unique_ids_and_addresses(self) -> Settings:
        for field in ("id", "address"):
            seen: dict[str, str] = {}
            for shutter in self.shutter:
                value = getattr(shutter, field)
                if value in seen:
                    raise ValueError(
                        f"duplicate {field} {value!r}: used by {seen[value]!r} and {shutter.id!r}"
                    )
                seen[value] = shutter.id
        return self

    @property
    def shutters(self) -> dict[str, ShutterConfig]:
        return {s.id: s for s in self.shutter}

    def by_address(self, address: str) -> ShutterConfig | None:
        wanted = address.strip().lower()
        return next((s for s in self.shutter if s.address == wanted), None)

    def manual_travel_seconds(self, shutter_id: str, direction: str) -> float | None:
        """What a person typed into shutters.toml, or None.

        This is the top of the precedence chain: a hand-written value beats any
        measurement, and the app never writes this file.
        """
        shutter = self.shutters[shutter_id]
        return shutter.travel_up_seconds if direction == "up" else shutter.travel_down_seconds

    def travel_seconds(self, shutter_id: str, direction: str) -> float:
        """Hand-written value where there is one, the stated default otherwise.

        Feature 002 layers measurements between the two; a tracker given a
        calibration service consults that instead of calling this directly.
        """
        manual = self.manual_travel_seconds(shutter_id, direction)
        return manual if manual is not None else self.general.default_travel_seconds


class ConfigError(RuntimeError):
    pass


def load_settings(path: str | Path) -> Settings:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(
            f"no configuration at {path}. Copy config/shutters.example.toml to {path} and edit it."
        )
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc
    try:
        return Settings.model_validate(raw)
    except Exception as exc:
        raise ConfigError(f"{path} is invalid:\n{exc}") from exc
