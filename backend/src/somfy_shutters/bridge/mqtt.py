"""The real adapter: Pi-Somfy over MQTT, as it speaks since v3.1.

This is the only file that knows topic names (constitution, principle II). Pi-Somfy's
Flask routes are not an API and are not touched. The contract this implements is
specs/006-pisomfy-mqtt-topics/contracts/mqtt.md; the old ``level/cmd`` and
``level/set_state`` topics no longer exist in Pi-Somfy.

Direction needs no translation: Pi-Somfy declares 100 = open, 0 = closed, which is the
convention of the whole app.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import AsyncIterator, Callable

import aiomqtt

from ..config import ADDRESS_PATTERN, BridgeConfig
from .base import MOVEMENT_STATES, BridgeUnreachable, Report, ShutterBridge

log = logging.getLogger(__name__)

PREFIX = "somfy"
COMMAND_TOPIC = PREFIX + "/{id}/command"
POSITION_REQUEST_TOPIC = PREFIX + "/{id}/set_position"
AVAILABILITY_TOPIC = PREFIX + "/bridge/availability"
DISCOVERY_TOPIC = "homeassistant/cover/+/config"
"""Inbound only. Those topics belong to the bridge; nothing is published there."""
COMMAND_TOPIC_RE = re.compile(r"^" + PREFIX + r"/([^/]+)/command$")

RECONNECT_START = 1.0
RECONNECT_MAX = 30.0


def publish_plan(verb: str, value: int | None = None) -> tuple[str, str]:
    """(topic template, payload) for a port call. Pure, so it can be tested alone.

    End stops go as the explicit OPEN/CLOSE commands; the bridge's position shortcut
    for 0 and 100 is not relied on. Stop is always the explicit STOP — a position equal
    to the bridge's belief makes it do nothing.
    """
    if verb == "stop":
        return COMMAND_TOPIC, "STOP"
    assert value is not None
    if value >= 100:
        return COMMAND_TOPIC, "OPEN"
    if value <= 0:
        return COMMAND_TOPIC, "CLOSE"
    return POSITION_REQUEST_TOPIC, str(value)


class MqttBridge(ShutterBridge):
    kind = "mqtt"

    SUBSCRIPTIONS = (
        PREFIX + "/+/position",
        PREFIX + "/+/state",
        AVAILABILITY_TOPIC,
        DISCOVERY_TOPIC,
    )
    """Nothing else. Discovery is read to learn the shutters (feature 005)."""

    def __init__(self, config: BridgeConfig) -> None:
        self._config = config
        self._client: aiomqtt.Client | None = None
        self._broker_up = False
        self._bridge_online: bool | None = None
        self._queue: asyncio.Queue[Report] = asyncio.Queue()
        self._callbacks: list[Callable[[bool], None]] = []
        self._task: asyncio.Task[None] | None = None
        self._unknown_addresses: set[str] = set()
        # lower-cased address -> how the bridge spells it in its topics
        self._spelling: dict[str, str] = {}
        # discovery topic -> the address it last announced, so that clearing the
        # topic can be understood as withdrawing that shutter
        self._announced: dict[str, str] = {}

    # --- port ----------------------------------------------------------------

    @property
    def connected(self) -> bool:
        """Reachable means the broker is up *and* the bridge announced itself online."""
        return self._broker_up and self._bridge_online is True

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def send_level(self, address: str, percent: int) -> None:
        await self._publish(address, *publish_plan("level", percent))

    async def send_stop(self, address: str) -> None:
        await self._publish(address, *publish_plan("stop"))

    async def reports(self) -> AsyncIterator[Report]:
        while True:
            yield await self._queue.get()

    def on_connection_change(self, callback: Callable[[bool], None]) -> None:
        self._callbacks.append(callback)

    # --- outbound ------------------------------------------------------------

    def _wire_id(self, address: str) -> str:
        return self._spelling.get(address.lower(), address)

    async def _publish(self, address: str, template: str, payload: str) -> None:
        client = self._client
        if client is None or not self._broker_up:
            raise BridgeUnreachable("no connection to the MQTT broker")
        if self._bridge_online is not True:
            raise BridgeUnreachable("Pi-Somfy has not announced itself online")
        try:
            # Not retained: a retained command would replay on the bridge's next
            # restart and move a shutter nobody asked to move.
            await client.publish(
                template.format(id=self._wire_id(address)), payload, qos=0, retain=False
            )
        except aiomqtt.MqttError as exc:
            # Deliberately not queued: a shutter closing twenty minutes late is
            # worse than one that never closed and said so.
            raise BridgeUnreachable(str(exc)) from exc

    # --- connection state ----------------------------------------------------

    def _changed(self, before: bool) -> None:
        after = self.connected
        if after != before:
            log.info("bridge %s", "reachable" if after else "unreachable")
            for callback in self._callbacks:
                callback(after)

    def _set_broker(self, up: bool) -> None:
        before = self.connected
        self._broker_up = up
        # A new broker session knows nothing yet; the retained availability arrives
        # right after subscribing.
        self._bridge_online = None
        self._changed(before)

    def _set_availability(self, online: bool) -> None:
        before = self.connected
        self._bridge_online = online
        self._changed(before)

    # --- inbound -------------------------------------------------------------

    def _handle(self, topic: str, payload: bytes | bytearray | str | None, retain: bool) -> None:
        """Turn one received message into a Report, an availability change, or nothing.

        ``retain`` is the flag of the *received* message: set only for what the broker
        delivers from its store on subscribe, so it means "old news".
        """
        try:
            text = payload if isinstance(payload, str) else bytes(payload or b"").decode()
        except UnicodeDecodeError:
            log.warning("undecodable payload on %s", topic)
            return
        text = text.strip()

        if topic == AVAILABILITY_TOPIC:
            if text in ("online", "offline"):
                self._set_availability(text == "online")
            else:
                log.warning("unknown availability %r", text)
            return

        if topic.startswith("homeassistant/"):
            report = self._parse_announcement(topic, text, retain)
            if report is not None:
                self._queue.put_nowait(report)
            return

        parts = topic.split("/")
        if len(parts) != 3 or parts[0] != PREFIX or parts[1] == "bridge":
            return
        wire_id, channel = parts[1], parts[2]
        address = wire_id.lower()

        if channel == "position":
            try:
                percent = int(float(text))
            except ValueError:
                log.warning("unparseable position %r on %s", text, topic)
                return
            if not 0 <= percent <= 100:
                log.warning("out-of-range position %s on %s", percent, topic)
                return
            self._spelling[address] = wire_id
            self._queue.put_nowait(Report(address, percent, retained=retain))
        elif channel == "state":
            if text not in MOVEMENT_STATES:
                log.warning("unknown state %r on %s", text, topic)
                return
            self._spelling[address] = wire_id
            self._queue.put_nowait(
                Report(address, kind="movement", state=text, retained=retain)  # type: ignore[arg-type]
            )

    def _parse_announcement(self, topic: str, text: str, retain: bool) -> Report | None:
        """One discovery message as an announcement, or None when it is not the bridge's.

        The address comes from ``command_topic`` — the only field carrying the bridge's own
        id; the topic's ``<bridge>_<id>`` segment is not relied on. Other integrations
        publish covers under the same prefix, so anything else is quietly ignored.
        """
        parts = topic.split("/")
        if len(parts) != 4 or parts[1] != "cover" or parts[3] != "config":
            return None
        if not text:
            # How a retained message is cleared. Current Pi-Somfy never does it, but a
            # later version clearing deleted shutters would mean exactly this.
            address = self._announced.pop(topic, None)
            if address is None:
                return None
            return Report(address, kind="announcement", name=None, retained=retain)
        try:
            payload = json.loads(text)
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        command_topic = payload.get("command_topic")
        match = COMMAND_TOPIC_RE.match(command_topic) if isinstance(command_topic, str) else None
        if match is None:
            return None
        wire_id = match.group(1)
        address = wire_id.lower()
        if not re.match(ADDRESS_PATTERN, address):
            log.warning("announcement with an address we cannot use: %r", wire_id)
            return None
        name = payload.get("name")
        device = payload.get("device")
        web_url = device.get("configuration_url") if isinstance(device, dict) else None
        self._spelling[address] = wire_id
        self._announced[topic] = address
        return Report(
            address,
            kind="announcement",
            name=name.strip() if isinstance(name, str) and name.strip() else wire_id,
            web_url=web_url if isinstance(web_url, str) and web_url else None,
            retained=retain,
        )

    async def _run(self) -> None:
        delay = RECONNECT_START
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self._config.host,
                    port=self._config.port,
                    username=self._config.user,
                    password=self._config.password,
                ) as client:
                    self._client = client
                    self._set_broker(True)
                    delay = RECONNECT_START
                    for subscription in self.SUBSCRIPTIONS:
                        await client.subscribe(subscription)
                    async for message in client.messages:
                        self._handle(str(message.topic), message.payload, bool(message.retain))
            except aiomqtt.MqttError as exc:
                log.warning("broker connection lost: %s; retrying in %.0fs", exc, delay)
            finally:
                self._client = None
                self._set_broker(False)
            await asyncio.sleep(delay)
            delay = min(RECONNECT_MAX, delay * 2)

    def note_unknown_address(self, address: str) -> None:
        """Log an unknown address once rather than on every message."""
        if address not in self._unknown_addresses:
            self._unknown_addresses.add(address)
            log.warning("report for address %s, which is not in our configuration", address)
