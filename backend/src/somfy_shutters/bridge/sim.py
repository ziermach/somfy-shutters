"""A simulated house.

This is what the app is developed against, because the motors are not paired yet
and because the interesting cases — drift, a command lost in the air, a restart
mid-travel — are painful to produce on real shutters.

The simulation deliberately knows things the app does not and must never learn
through the port: a soft-start dead time, a non-linear travel curve, and
different speeds up and down. If the app could see these, testing against the
simulator would prove nothing.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import random
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from .base import BridgeUnreachable, Report, ShutterBridge

REPORT_INTERVAL = 1.0
"""Pi-Somfy publishes sparsely; once a second while travelling is generous."""


def travel_curve(progress: float, k: float) -> float:
    """Slats stack at the top and tilt at the bottom, so travel is not linear in time."""
    return progress - (k * math.sin(2 * math.pi * progress)) / (2 * math.pi)


@dataclass
class SimShutter:
    address: str
    dead_time: float = 0.6
    travel_up: float = 17.4
    travel_down: float = 15.5
    curve_k: float = 0.55
    percent: float = 100.0

    target: float = 100.0
    started_at: float | None = None
    start_percent: float = 100.0

    def command(self, percent: int, now: float) -> None:
        if percent == round(self.percent):
            return
        self.start_percent = self.percent
        self.target = float(percent)
        self.started_at = now

    def advance(self, now: float) -> None:
        if self.started_at is None:
            return
        span = self.target - self.start_percent
        duration = self.travel_up if span > 0 else self.travel_down
        duration *= abs(span) / 100.0
        elapsed = now - self.started_at
        if elapsed <= self.dead_time:
            return
        progress = min(1.0, (elapsed - self.dead_time) / duration) if duration > 0 else 1.0
        self.percent = self.start_percent + span * travel_curve(progress, self.curve_k)
        if progress >= 1.0:
            self.percent = self.target
            self.started_at = None


@dataclass
class SimBridge(ShutterBridge):
    """Implements the port. The fields above are invisible through it."""

    addresses: list[str]
    loss_rate: float = 0.0
    kind: str = "sim"

    _shutters: dict[str, SimShutter] = field(default_factory=dict)
    _queue: asyncio.Queue[Report] = field(default_factory=asyncio.Queue)
    _connected: bool = True
    _task: asyncio.Task[None] | None = None
    _callbacks: list[Callable[[bool], None]] = field(default_factory=list)
    _rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        # Each window differs, the way real ones do.
        for index, address in enumerate(self.addresses):
            spread = index % 4
            self._shutters[address] = SimShutter(
                address=address,
                dead_time=0.5 + spread * 0.08,
                travel_up=12.0 + spread * 2.1,
                travel_down=10.8 + spread * 1.8,
                curve_k=0.40 + spread * 0.05,
                percent=100.0 if index % 2 == 0 else 0.0,
            )

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
        if not self._connected:
            raise BridgeUnreachable("simulated bridge is offline")
        shutter = self._shutters.get(address)
        if shutter is None:
            return
        # A lost command is indistinguishable from a delivered one on one-way radio:
        # the caller still succeeds, and the shutter simply never moves.
        if self._rng.random() < self.loss_rate:
            return
        shutter.command(percent, time.monotonic())

    async def _run(self) -> None:
        while True:
            now = time.monotonic()
            for shutter in self._shutters.values():
                moving = shutter.started_at is not None
                shutter.advance(now)
                if moving:
                    await self._queue.put(Report(shutter.address, round(shutter.percent)))
            await asyncio.sleep(REPORT_INTERVAL)

    async def reports(self) -> AsyncIterator[Report]:
        while True:
            yield await self._queue.get()

    def on_connection_change(self, callback: Callable[[bool], None]) -> None:
        self._callbacks.append(callback)

    # --- controls the real bridge does not have, used by the sim-only endpoints ---

    def set_connected(self, connected: bool) -> None:
        if connected != self._connected:
            self._connected = connected
            for callback in self._callbacks:
                callback(connected)

    async def inject_report(self, address: str, percent: int) -> None:
        await self._queue.put(Report(address, percent))

    def truth(self, address: str) -> float:
        """Only for tests and the quickstart — never reachable through the port."""
        return self._shutters[address].percent
