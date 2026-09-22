"""The port to whatever moves the shutters.

Nothing on this side of the boundary knows about MQTT, topics, RTS, rolling codes
or 433.42 MHz. That vocabulary lives in bridge/mqtt.py alone, which is what makes
the transmitter swappable (constitution, principle II).
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Literal

ReportKind = Literal["position", "movement", "announcement"]
MovementState = Literal["opening", "closing", "open", "closed", "stopped"]
MOVEMENT_STATES: frozenset[str] = frozenset({"opening", "closing", "open", "closed", "stopped"})


@dataclass(frozen=True)
class Report:
    """What the bridge says about a shutter: a position, that it moves or stands, or
    that it exists.

    Not a measurement. Pi-Somfy computes positions from its own configured travel
    time, so a position is a second estimate of unknown quality — see feature 001's
    research, section 5. ``retained`` marks old news: a report the broker kept and
    delivered on connect, not something that just happened (feature 006).

    An ``announcement`` (feature 005) says the bridge knows a shutter by this address
    and name — never that a motor answers to it. ``name`` None means the bridge
    withdrew it; ``web_url`` is where the bridge's own interface is, if it says.
    """

    address: str
    percent: int | None = None
    kind: ReportKind = "position"
    state: MovementState | None = None
    retained: bool = False
    name: str | None = None
    web_url: str | None = None


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
    async def send_stop(self, address: str) -> None:
        """Ask the shutter to stop where it is. Raises BridgeUnreachable likewise.

        A separate verb, not a position: the bridge ignores a position equal to its
        own belief, so "go to where you are" would let the shutter run on.
        Success means handed over — never that the motor stopped.
        """

    @abc.abstractmethod
    def reports(self) -> AsyncIterator[Report]: ...

    @abc.abstractmethod
    def on_connection_change(self, callback: Callable[[bool], None]) -> None: ...
