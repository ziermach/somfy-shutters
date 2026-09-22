"""Feature 006: the MQTT adapter speaks Pi-Somfy's current interface.

Every topic, payload and flag in specs/006-pisomfy-mqtt-topics/contracts/mqtt.md, asserted
without a broker: a fake client records what would be published, and inbound messages are
fed to the adapter's pure handler exactly as aiomqtt would deliver them.
"""

from __future__ import annotations

import pytest

from somfy_shutters.bridge.base import BridgeUnreachable, Report
from somfy_shutters.bridge.mqtt import MqttBridge
from somfy_shutters.config import BridgeConfig

ADDRESS = "0x279621"


class FakeClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, int, bool]] = []

    async def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> None:
        self.published.append((topic, payload, qos, retain))


def bridge(online: bool = True) -> tuple[MqttBridge, FakeClient]:
    b = MqttBridge(BridgeConfig(kind="mqtt"))
    client = FakeClient()
    b._client = client  # type: ignore[assignment]
    b._set_broker(True)
    if online:
        b._handle("somfy/bridge/availability", b"online", True)
    return b, client


def drain(b: MqttBridge) -> list[Report]:
    out = []
    while not b._queue.empty():
        out.append(b._queue.get_nowait())
    return out


# --- US1: commands -------------------------------------------------------------


@pytest.mark.parametrize(
    ("percent", "topic", "payload"),
    [
        (100, "somfy/0x279621/command", "OPEN"),
        (0, "somfy/0x279621/command", "CLOSE"),
        (37, "somfy/0x279621/set_position", "37"),
        (1, "somfy/0x279621/set_position", "1"),
        (99, "somfy/0x279621/set_position", "99"),
    ],
)
async def test_levels_become_the_bridge_commands(percent, topic, payload) -> None:
    b, client = bridge()
    await b.send_level(ADDRESS, percent)
    assert client.published == [(topic, payload, 0, False)], "QoS 0, never retained"


async def test_nothing_is_sent_while_the_broker_is_down() -> None:
    b, client = bridge()
    b._set_broker(False)
    with pytest.raises(BridgeUnreachable):
        await b.send_level(ADDRESS, 100)
    assert client.published == []


async def test_nothing_is_sent_before_the_bridge_announced_itself() -> None:
    b, client = bridge(online=False)
    with pytest.raises(BridgeUnreachable):
        await b.send_level(ADDRESS, 100)
    assert client.published == []


async def test_commands_use_the_spelling_the_bridge_uses() -> None:
    b, client = bridge()
    b._handle("somfy/0X279621/position", b"50", True)
    await b.send_level(ADDRESS, 0)
    assert client.published[-1][0] == "somfy/0X279621/command"


# --- US2: stop -----------------------------------------------------------------


async def test_stop_is_the_explicit_command_never_a_position() -> None:
    b, client = bridge()
    await b.send_stop(ADDRESS)
    assert client.published == [("somfy/0x279621/command", "STOP", 0, False)]
    assert not any(topic.endswith("/set_position") for topic, *_ in client.published)


async def test_stop_is_refused_when_the_bridge_is_offline() -> None:
    b, _ = bridge()
    b._handle("somfy/bridge/availability", b"offline", False)
    with pytest.raises(BridgeUnreachable):
        await b.send_stop(ADDRESS)


# --- US3: reports --------------------------------------------------------------


def test_a_position_report() -> None:
    b, _ = bridge()
    b._handle("somfy/0x279621/position", b"48", False)
    assert drain(b) == [Report(ADDRESS, 48, retained=False)]


def test_the_retain_flag_marks_old_news() -> None:
    b, _ = bridge()
    b._handle("somfy/0x279621/position", b"100", True)
    b._handle("somfy/0x279621/state", b"open", True)
    assert drain(b) == [
        Report(ADDRESS, 100, retained=True),
        Report(ADDRESS, kind="movement", state="open", retained=True),
    ]


@pytest.mark.parametrize("state", ["opening", "closing", "open", "closed", "stopped"])
def test_every_movement_word(state) -> None:
    b, _ = bridge()
    b._handle("somfy/0x279621/state", state.encode(), False)
    assert drain(b) == [Report(ADDRESS, kind="movement", state=state)]


def test_ids_are_matched_case_insensitively() -> None:
    b, _ = bridge()
    b._handle("somfy/0X279621/position", b"20", False)
    assert drain(b)[0].address == ADDRESS


@pytest.mark.parametrize(
    ("topic", "payload"),
    [
        ("somfy/0x279621/position", b"half"),
        ("somfy/0x279621/position", b"101"),
        ("somfy/0x279621/position", b"-1"),
        ("somfy/0x279621/state", b"dancing"),
        ("somfy/0x279621/position/extra", b"10"),
        ("somfy/0x279621/level/set_state", b"10"),
        ("other/0x279621/position", b"10"),
        ("homeassistant/cover/pi_0x279621/config", b"{}"),
    ],
)
def test_malformed_or_foreign_messages_are_dropped(topic, payload) -> None:
    b, _ = bridge()
    b._handle(topic, payload, False)
    assert drain(b) == []


def test_only_the_current_topics_are_subscribed() -> None:
    assert MqttBridge.SUBSCRIPTIONS == (
        "somfy/+/position",
        "somfy/+/state",
        "somfy/bridge/availability",
    )


# --- US4: availability ---------------------------------------------------------


def test_reachable_needs_broker_and_bridge() -> None:
    b = MqttBridge(BridgeConfig(kind="mqtt"))
    seen: list[bool] = []
    b.on_connection_change(seen.append)

    b._set_broker(True)
    assert b.connected is False, "no availability announced yet"
    b._handle("somfy/bridge/availability", b"online", True)
    assert b.connected is True
    b._handle("somfy/bridge/availability", b"offline", False)
    assert b.connected is False
    b._handle("somfy/bridge/availability", b"online", False)
    b._set_broker(False)
    assert b.connected is False
    assert seen == [True, False, True, False], "one callback per change of the combined value"


def test_a_broker_reconnect_forgets_availability_until_it_is_announced_again() -> None:
    b, _ = bridge()
    b._set_broker(False)
    b._set_broker(True)
    assert b.connected is False
    b._handle("somfy/bridge/availability", b"online", True)
    assert b.connected is True


def test_availability_is_not_a_report() -> None:
    b, _ = bridge()
    b._handle("somfy/bridge/availability", b"offline", False)
    assert drain(b) == []
