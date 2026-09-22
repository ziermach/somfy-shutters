"""The real adapter: Pi-Somfy over MQTT.

Two topics, and that is the whole integration surface. Pi-Somfy's Flask routes
are not an API and are not touched (constitution, principle II).

This file is also the single place that knows which direction the wire uses.
See contracts/mqtt.md: flipping ``invert_level`` must be sufficient on its own to
correct the entire system.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable

import aiomqtt

from ..config import BridgeConfig
from .base import BridgeUnreachable, Report, ShutterBridge

log = logging.getLogger(__name__)

CMD_TOPIC = "somfy/{address}/level/cmd"
STATE_TOPIC = "somfy/{address}/level/set_state"
STATE_WILDCARD = "somfy/+/level/set_state"

RECONNECT_START = 1.0
RECONNECT_MAX = 30.0


class MqttBridge(ShutterBridge):
    kind = "mqtt"

    def __init__(self, config: BridgeConfig) -> None:
        self._config = config
        self._client: aiomqtt.Client | None = None
        self._connected = False
        self._queue: asyncio.Queue[Report] = asyncio.Queue()
        self._callbacks: list[Callable[[bool], None]] = []
        self._task: asyncio.Task[None] | None = None
        self._unknown_addresses: set[str] = set()

    # --- level translation, the only place it happens ------------------------

    def _to_wire(self, percent: int) -> int:
        return 100 - percent if self._config.invert_level else percent

    def _from_wire(self, value: int) -> int:
        return 100 - value if self._config.invert_level else value

    # --- port ----------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def send_level(self, address: str, percent: int) -> None:
        client = self._client
        if client is None or not self._connected:
            raise BridgeUnreachable("no connection to the MQTT broker")
        try:
            await client.publish(CMD_TOPIC.format(address=address), str(self._to_wire(percent)))
        except aiomqtt.MqttError as exc:
            # Deliberately not queued: a shutter closing twenty minutes late is
            # worse than one that never closed and said so.
            raise BridgeUnreachable(str(exc)) from exc

    async def send_stop(self, address: str) -> None:
        client = self._client
        if client is None or not self._connected:
            raise BridgeUnreachable("no connection to the MQTT broker")
        try:
            await client.publish(f"somfy/{address}/command", "STOP")
        except aiomqtt.MqttError as exc:
            raise BridgeUnreachable(str(exc)) from exc

    async def reports(self) -> AsyncIterator[Report]:
        while True:
            yield await self._queue.get()

    def on_connection_change(self, callback: Callable[[bool], None]) -> None:
        self._callbacks.append(callback)

    # --- internals -----------------------------------------------------------

    def _set_connected(self, connected: bool) -> None:
        if connected == self._connected:
            return
        self._connected = connected
        log.info("bridge %s", "connected" if connected else "disconnected")
        for callback in self._callbacks:
            callback(connected)

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
                    self._set_connected(True)
                    delay = RECONNECT_START
                    await client.subscribe(STATE_WILDCARD)
                    async for message in client.messages:
                        self._handle(str(message.topic), message.payload)
            except aiomqtt.MqttError as exc:
                log.warning("bridge connection lost: %s; retrying in %.0fs", exc, delay)
            finally:
                self._client = None
                self._set_connected(False)
            await asyncio.sleep(delay)
            delay = min(RECONNECT_MAX, delay * 2)

    def _handle(self, topic: str, payload: bytes | bytearray | str | None) -> None:
        parts = topic.split("/")
        if len(parts) != 4:
            return
        address = parts[1]
        try:
            raw = int(
                float(payload if isinstance(payload, str) else bytes(payload or b"").decode())
            )
        except (ValueError, UnicodeDecodeError):
            log.warning("unparseable payload on %s: %r", topic, payload)
            return
        if not 0 <= raw <= 100:
            log.warning("out-of-range level %s on %s", raw, topic)
            return
        self._queue.put_nowait(Report(address=address, percent=self._from_wire(raw)))

    def note_unknown_address(self, address: str) -> None:
        """Log an unknown address once rather than on every message."""
        if address not in self._unknown_addresses:
            self._unknown_addresses.add(address)
            log.warning("report for address %s, which is not in our configuration", address)
