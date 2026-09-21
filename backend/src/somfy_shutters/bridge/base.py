"""The port to whatever moves the shutters.

Nothing on this side of the boundary knows about MQTT, topics, RTS, rolling codes
or 433.42 MHz. That vocabulary lives in bridge/mqtt.py alone, which is what makes
the transmitter swappable (constitution, principle II).
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Report:
    """A position another party claims a shutter is at.

    Not a measurement. Pi-Somfy computes this from its own configured travel time,
    so it is a second estimate of unknown quality — see research.md, section 5.
    """

    address: str
    percent: int


class BridgeUnreachable(RuntimeError):
    """The command could not be handed over. Nothing is queued for later."""


class ShutterBridge(abc.ABC):
    kind: str

    @property
    @abc.abstractmethod
    def connected(self) -> bool: ...

    @abc.abstractmethod
    async def start(self) -> None: ...

    @abc.abstractmethod
    async def stop(self) -> None: ...

    @abc.abstractmethod
    async def send_level(self, address: str, percent: int) -> None:
        """Ask for a position. Raises BridgeUnreachable if it could not be handed over.

        Success means the message was accepted for delivery — never that a motor
        moved. The radio is one-way; there is nothing to acknowledge.
        """

    @abc.abstractmethod
    def reports(self) -> AsyncIterator[Report]: ...

    @abc.abstractmethod
    def on_connection_change(self, callback: Callable[[bool], None]) -> None: ...
