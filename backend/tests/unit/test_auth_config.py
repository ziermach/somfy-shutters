"""T002, T014: the [auth] section and the simulator exemption (FR-029)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from somfy_shutters.config import Settings

from ..conftest import CONFIG

EXAMPLE = Path(__file__).resolve().parents[3] / "config" / "shutters.example.toml"


def settings(bridge: str, **auth) -> Settings:
    return Settings.model_validate({**CONFIG, "bridge": {"kind": bridge}, "auth": auth})


def test_simulator_defaults_to_open() -> None:
    assert settings("sim").auth.mode == "open"
    assert settings("sim").auth.required is False


def test_real_bridge_defaults_to_required() -> None:
    assert settings("mqtt").auth.mode == "required"


def test_simulator_can_be_made_required() -> None:
    assert settings("sim", mode="required").auth.required is True


def test_open_with_a_real_bridge_refuses_to_load() -> None:
    with pytest.raises(ValidationError, match="nur mit dem Simulator"):
        settings("mqtt", mode="open")


def test_defaults() -> None:
    auth = settings("sim").auth
    assert (auth.failed_attempts, auth.failed_window_minutes, auth.lockout_minutes) == (10, 5, 15)
    assert (auth.command_burst, auth.command_per_second) == (10, 1.0)
    assert (auth.pairing_minutes, auth.audit_retention_days) == (5, 180)
    assert auth.trusted_proxy is None


def test_the_example_config_loads() -> None:
    raw = tomllib.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert Settings.model_validate(raw).auth.mode == "open"


def test_loading_a_real_bridge_config_with_open_mode_fails_with_the_setting(tmp_path) -> None:
    from somfy_shutters.config import ConfigError, load_settings

    text = EXAMPLE.read_text(encoding="utf-8").replace('kind = "sim"', 'kind = "mqtt"')
    text = text.replace('# mode = "required"', 'mode = "open"')
    path = tmp_path / "shutters.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match=r'auth\.mode = "open" ist nur mit dem Simulator'):
        load_settings(path)
