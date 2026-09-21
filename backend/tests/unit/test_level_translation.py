"""T015: the direction question lives in exactly one file.

Open hardware question 1 has not been measured. The acceptance criterion in
contracts/mqtt.md is that flipping invert_level is sufficient on its own — so
that is what this asserts.
"""

from __future__ import annotations

import pytest

from somfy_shutters.bridge.mqtt import MqttBridge
from somfy_shutters.config import BridgeConfig


@pytest.mark.parametrize("percent", [0, 1, 30, 62, 99, 100])
def test_round_trip_without_inversion(percent: int) -> None:
    bridge = MqttBridge(BridgeConfig(invert_level=False))
    assert bridge._from_wire(bridge._to_wire(percent)) == percent


@pytest.mark.parametrize("percent", [0, 1, 30, 62, 99, 100])
def test_round_trip_with_inversion(percent: int) -> None:
    bridge = MqttBridge(BridgeConfig(invert_level=True))
    assert bridge._from_wire(bridge._to_wire(percent)) == percent


def test_inversion_actually_reverses_the_wire() -> None:
    plain = MqttBridge(BridgeConfig(invert_level=False))
    flipped = MqttBridge(BridgeConfig(invert_level=True))
    assert plain._to_wire(100) == 100
    assert flipped._to_wire(100) == 0
    assert plain._from_wire(0) == 0
    assert flipped._from_wire(0) == 100


def test_translation_lives_only_in_the_adapter() -> None:
    """Nothing outside bridge/mqtt.py may mention invert_level."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "somfy_shutters"
    offenders = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if "invert_level" in path.read_text()
        and path.name != "mqtt.py"
        and path.name != "config.py"
    ]
    assert offenders == [], f"invert_level leaked into {offenders}"
