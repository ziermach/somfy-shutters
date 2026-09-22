"""A simulated house.

This is what the app is developed against, because the motors are not paired yet
and because the interesting cases — drift, a command lost in the air, a restart
mid-travel — are painful to produce on real shutters.

The simulation deliberately knows things the app does not and must never learn
through the port: a soft-start dead time, a non-linear travel curve, and
different speeds up and down.

Two things here are modelled the way the real chain works, and both matter:

**The motor runs on time, not on position.** A command to 50 % makes the bridge
run the motor for half a travel time. Because the motor does not move at a
constant rate, the shutter then sits somewhere that is *not* the middle of the
window. An earlier version applied the travel curve to the commanded span, so
every partial command landed exactly on target and the whole class of error
feature 002's verification exists to correct could not occur at all.

**The bridge reports its own guess, not the truth.** Pi-Somfy publishes a
position computed from its own configured travel time, linearly. If the
simulator reported the true position instead, the app would simply be told the
answer it is supposed to measure.
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


def inverse_travel_curve(fraction: float, k: float) -> float:
    """How much motor time a given position corresponds to.

    The curve is monotonic for |k| < 1, so a bisection is exact enough and needs
    no algebra that could be got subtly wrong.
    """
    fraction = min(1.0, max(0.0, fraction))
    low, high = 0.0, 1.0
    for _ in range(40):
        middle = (low + high) / 2
        if travel_curve(middle, k) < fraction:
            low = middle
        else:
            high = middle
    return (low + high) / 2


@dataclass
class SimShutter:
    address: str
    dead_time: float = 0.6
    travel_up: float = 17.4
    travel_down: float = 15.5
    curve_k: float = 0.55

    percent: float = 100.0
    """Where the shutter physically is. Nothing outside this module may read it."""

    believed: float = 100.0
    """What the bridge thinks, computed linearly. This is what it publishes."""

    started_at: float | None = None
    direction: int = 0
    run_seconds: float = 0.0
    start_motor_time: float = 0.0
    start_believed: float = 100.0
    target_believed: float = 100.0

    # --- the physical window -------------------------------------------------

    def _full_time(self, direction: int) -> float:
        return self.travel_up if direction > 0 else self.travel_down

    def _motor_time_of(self, percent: float, direction: int) -> float:
        """Seconds of travel in this direction between the end stop and `percent`."""
        fraction = percent / 100 if direction > 0 else 1 - percent / 100
        return inverse_travel_curve(fraction, self.curve_k) * self._full_time(direction)

    def _percent_at(self, motor_time: float, direction: int) -> float:
        full = self._full_time(direction)
        progress = min(1.0, max(0.0, motor_time / full)) if full else 1.0
        fraction = travel_curve(progress, self.curve_k)
        return 100 * fraction if direction > 0 else 100 * (1 - fraction)

    # --- being commanded -----------------------------------------------------

    def command(self, percent: int, now: float) -> None:
        if percent == round(self.believed):
            return
        self.direction = 1 if percent > self.believed else -1
        # The bridge runs the motor for as long as *its* estimate says it should.
        self.run_seconds = abs(percent - self.believed) / 100 * self._full_time(self.direction)
        self.start_believed = self.believed
        self.target_believed = float(percent)
        self.start_motor_time = self._motor_time_of(self.percent, self.direction)
        self.started_at = now

    def advance(self, now: float) -> None:
        if self.started_at is None:
            return
        elapsed = now - self.started_at
        if elapsed <= self.dead_time:
            return

        ran = min(elapsed - self.dead_time, self.run_seconds)
        self.percent = self._percent_at(self.start_motor_time + ran, self.direction)
        progress = ran / self.run_seconds if self.run_seconds else 1.0
        self.believed = (
            self.start_believed + (self.target_believed - self.start_believed) * progress
        )

        if elapsed - self.dead_time >= self.run_seconds:
            self.started_at = None
            if self.target_believed in (0.0, 100.0):
                # The motor reaches the mechanical stop whatever anyone believed.
                self.percent = self.target_believed
            self.believed = self.target_believed


@dataclass
class SimBridge(ShutterBridge):
    """Implements the port. Everything above is invisible through it."""

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
            start = 100.0 if index % 2 == 0 else 0.0
            self._shutters[address] = SimShutter(
                address=address,
                dead_time=0.5 + spread * 0.08,
                travel_up=12.0 + spread * 2.1,
                travel_down=10.8 + spread * 1.8,
                curve_k=0.40 + spread * 0.05,
                percent=start,
                believed=start,
                start_believed=start,
                target_believed=start,
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
                    # Its own dead reckoning, not the truth — the app has to cope
                    # with a second estimate, which is what it will get in the house.
                    await self._queue.put(Report(shutter.address, round(shutter.believed)))
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

    def place(self, address: str, percent: float) -> None:
        """Put a simulated window somewhere, for tests that need a known start."""
        shutter = self._shutters[address]
        shutter.percent = percent
        shutter.believed = percent
        shutter.start_believed = percent
        shutter.target_believed = percent
        shutter.started_at = None
