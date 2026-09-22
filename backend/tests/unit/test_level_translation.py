"""Feature 006: the direction switch is retired.

Pi-Somfy v3.1 declares 100 = open, 0 = closed — the app's own convention — so no
translation happens anywhere. `invert_level` stays readable so older configs validate,
changes nothing, and says so once at start.
"""

from __future__ import annotations

import logging
from pathlib import Path

from somfy_shutters.bridge.mqtt import publish_plan
from somfy_shutters.bridge.sim import SimBridge
from somfy_shutters.config import Settings
from somfy_shutters.main import create_app
from somfy_shutters.store import Store

from ..conftest import CONFIG


def test_an_old_config_with_invert_level_still_validates() -> None:
    config = {**CONFIG, "bridge": {"kind": "sim", "invert_level": True}}
    assert Settings.model_validate(config).bridge.invert_level is True


def test_invert_level_changes_nothing_on_the_wire() -> None:
    assert publish_plan("level", 100) == ("somfy/{id}/command", "OPEN")
    assert publish_plan("level", 0) == ("somfy/{id}/command", "CLOSE")


def test_it_is_logged_once_at_start(tmp_path, caplog) -> None:
    settings = Settings.model_validate({**CONFIG, "bridge": {"kind": "sim", "invert_level": True}})
    with caplog.at_level(logging.WARNING):
        create_app(
            settings, store=Store(tmp_path / "s.db"), bridge=SimBridge(addresses=["0x279621"])
        )
    assert sum("invert_level" in r.message for r in caplog.records) == 1


def test_nothing_outside_config_and_main_mentions_it() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "somfy_shutters"
    offenders = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if "invert_level" in path.read_text() and path.name not in {"config.py", "main.py"}
    ]
    assert offenders == [], f"invert_level is used in {offenders}"
