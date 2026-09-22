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
import random
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from .base import BridgeUnreachable, Report, ShutterBridge

REPORT_INTERVAL = 1.0
"""Pi-Somfy publishes sparsely; once a second while travelling is generous."""


def travel_curve(progress: float, a: float) -> float:
    """Slats stack at the top and tilt at the bottom, so travel is not linear in time.

    The app uses the same family (calibration.travel_curve) but has to discover
    the exponent; here it is a property of the window that nothing reveals.
    """
    return progress**a


def inverse_travel_curve(fraction: float, a: float) -> float:
    """How much motor time a given position corresponds to."""
    return min(1.0, max(0.0, fraction)) ** (1 / a)


@dataclass
class SimShutter:
    address: str
    dead_time: float = 0.6
    travel_up: float = 17.4
    travel_down: float = 15.5
    curve_a: float = 1.25

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
        return inverse_travel_curve(fraction, self.curve_a) * self._full_time(direction)

    def _percent_at(self, motor_time: float, direction: int) -> float:
        full = self._full_time(direction)
        progress = min(1.0, max(0.0, motor_time / full)) if full else 1.0
        fraction = travel_curve(progress, self.curve_a)
        return 100 * fraction if direction > 0 else 100 * (1 - fraction)

    # --- being commanded -----------------------------------------------------

    def command(self, percent: int, now: float) -> None:
        if percent == round(self.believed):
            if percent in (0, 100):
                # OPEN or CLOSE towards where the count already is: the motor turns
                # that way, so a running travel the other way ends — "auf" right after
                # "zu" must not let the close run all the way down.
                self.started_at = None
            # A partial position equal to the bridge's belief does nothing at all.
            # That is how current Pi-Somfy behaves, and why stop is its own verb.
            return
        self.direction = 1 if percent > self.believed else -1
        # The bridge runs the motor for as long as *its* estimate says it should.
        self.run_seconds = abs(percent - self.believed) / 100 * self._full_time(self.direction)
        self.start_believed = self.believed
        self.target_believed = float(percent)
        self.start_motor_time = self._motor_time_of(self.percent, self.direction)
        self.started_at = now

    def halt(self, now: float) -> None:
        """STOP: the motor stops where it is, and the bridge's count stops with it."""
        self.advance(now)
        if self.started_at is not None:
            self.started_at = None
            self.target_believed = self.believed

    @property
    def moving(self) -> bool:
        return self.started_at is not None

    def state_word(self) -> str:
        if self.moving:
            return "opening" if self.direction > 0 else "closing"
        if round(self.believed) >= 100:
            return "open"
        if round(self.believed) <= 0:
            return "closed"
        return "stopped"

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
class BridgeEntry:
    """A shutter as the simulated bridge itself knows it (feature 005)."""

    name: str
    enabled: bool = True
    listening: bool = True
    """Subscribed to its command topics. Pi-Somfy subscribes only when it connects to
    the broker, so a shutter added in its interface ignores commands until a restart."""


@dataclass
class SimBridge(ShutterBridge):
    """Implements the port. Everything above is invisible through it."""

    addresses: list[str]
    loss_rate: float = 0.0
    kind: str = "sim"
    names: dict[str, str] = field(default_factory=dict)
    """Display names the bridge announces; an address without one is announced by
    its address, as Pi-Somfy would with an unnamed shutter."""

    _shutters: dict[str, SimShutter] = field(default_factory=dict)
    _queue: asyncio.Queue[Report] = field(default_factory=asyncio.Queue)
    _connected: bool = True
    _task: asyncio.Task[None] | None = None
    _callbacks: list[Callable[[bool], None]] = field(default_factory=list)
    _rng: random.Random = field(default_factory=random.Random)
    _bridge: dict[str, BridgeEntry] = field(default_factory=dict)
    # What the broker keeps under the discovery topics: never withdrawn by the bridge.
    _retained_announcements: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for address in self.addresses:
            self._add_window(address)
            name = self.names.get(address, address)
            self._bridge[address] = BridgeEntry(name=name)
            self._retained_announcements[address] = name

    def _add_window(self, address: str) -> None:
        # Each window differs, the way real ones do.
        index = len(self._shutters)
        spread = index % 4
        start = 100.0 if index % 2 == 0 else 0.0
        self._shutters[address] = SimShutter(
            address=address,
            dead_time=0.5 + spread * 0.08,
            travel_up=12.0 + spread * 2.1,
            travel_down=10.8 + spread * 1.8,
            curve_a=1.1 + spread * 0.12,
            percent=start,
            believed=start,
            start_believed=start,
            target_believed=start,
        )

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        # What a broker hands a new subscriber: every announcement ever made, then
        # every shutter's last position and state, kept from before. Old news, and
        # marked as such (features 005 and 006).
        for address, name in self._retained_announcements.items():
            await self._queue.put(self._announcement(address, name, retained=True))
        for shutter in self._shutters.values():
            await self._queue.put(Report(shutter.address, round(shutter.believed), retained=True))
            await self._queue.put(
                Report(shutter.address, kind="movement", state=shutter.state_word(), retained=True)
            )
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
        if shutter is None or not self._listens(address):
            return
        # A lost command is indistinguishable from a delivered one on one-way radio:
        # the caller still succeeds, and the shutter simply never moves.
        if self._rng.random() < self.loss_rate:
            return
        now = time.monotonic()
        # Brought up to date first: the loop only steps once a second, and a
        # command mid-travel has to start from where the motor is now, not from
        # where it was at the last step.
        shutter.advance(now)
        was_moving = shutter.moving
        shutter.command(percent, now)
        if shutter.moving:
            await self._movement(shutter)
        elif was_moving:
            await self._settled(shutter)

    async def send_stop(self, address: str) -> None:
        if not self._connected:
            raise BridgeUnreachable("simulated bridge is offline")
        shutter = self._shutters.get(address)
        if shutter is None or not self._listens(address) or self._rng.random() < self.loss_rate:
            return
        was_moving = shutter.moving
        shutter.halt(time.monotonic())
        if was_moving:
            await self._settled(shutter)

    async def _movement(self, shutter: SimShutter) -> None:
        await self._queue.put(Report(shutter.address, kind="movement", state=shutter.state_word()))

    async def _settled(self, shutter: SimShutter) -> None:
        """What Pi-Somfy publishes when a travel ends: the position, then the state."""
        await self._queue.put(Report(shutter.address, round(shutter.believed)))
        await self._movement(shutter)

    async def _run(self) -> None:
        while True:
            now = time.monotonic()
            for shutter in self._shutters.values():
                moving = shutter.moving
                shutter.advance(now)
                if moving and shutter.moving:
                    # Its own dead reckoning, not the truth — the app has to cope
                    # with a second estimate, which is what it will get in the house.
                    await self._queue.put(Report(shutter.address, round(shutter.believed)))
                elif moving:
                    await self._settled(shutter)
            await asyncio.sleep(REPORT_INTERVAL)

    async def reports(self) -> AsyncIterator[Report]:
        while True:
            yield await self._queue.get()

    def on_connection_change(self, callback: Callable[[bool], None]) -> None:
        self._callbacks.append(callback)

    def _listens(self, address: str) -> bool:
        entry = self._bridge.get(address)
        return entry is not None and entry.enabled and entry.listening

    def _announcement(self, address: str, name: str, *, retained: bool) -> Report:
        return Report(address, kind="announcement", name=name, retained=retained)

    # --- controls the real bridge does not have, used by the sim-only endpoints ---

    def set_connected(self, connected: bool) -> None:
        if connected != self._connected:
            self._connected = connected
            for callback in self._callbacks:
                callback(connected)
            if connected:
                # Pi-Somfy's on_connect: announce every shutter it knows, live, and
                # subscribe to their commands (feature 005, research §1).
                for address, entry in self._bridge.items():
                    if not entry.enabled:
                        continue
                    entry.listening = True
                    self._retained_announcements[address] = entry.name
                    self._queue.put_nowait(self._announcement(address, entry.name, retained=False))

    def bridge_add(self, name: str) -> str:
        """A person creates a shutter in the bridge's interface. Announced — and
        commandable — only after the bridge's next restart, as in Pi-Somfy."""
        known = [int(a, 16) for a in self._bridge] or [0x279620]
        address = f"0x{max(known) + 1:06x}"
        self._add_window(address)
        self._bridge[address] = BridgeEntry(name=name, listening=False)
        return address

    def bridge_delete(self, address: str) -> bool:
        """A person deletes a shutter in the bridge. Its retained announcement stays."""
        entry = self._bridge.get(address)
        if entry is None or not entry.enabled:
            return False
        entry.enabled = False
        return True

    def bridge_restart(self) -> None:
        self.set_connected(False)
        self.set_connected(True)

    def bridge_shutters(self) -> list[dict[str, object]]:
        return [
            {"address": a, "name": e.name, "enabled": e.enabled, "listening": e.listening}
            for a, e in self._bridge.items()
        ]

    async def inject_report(self, address: str, percent: int) -> None:
        await self._queue.put(Report(address, percent))

    def truth(self, address: str) -> float:
        """Only for tests and the quickstart — never reachable through the port."""
        return self._shutters[address].percent

    def place(self, address: str, percent: float, believed: float | None = None) -> None:
        """Put a simulated window somewhere: for tests that need a known start, and
        on startup, where the house stays where the app last knew it."""
        shutter = self._shutters.get(address)
        if shutter is None:
            return
        counter = percent if believed is None else believed
        shutter.percent = percent
        shutter.believed = counter
        shutter.start_believed = counter
        shutter.target_believed = counter
        shutter.started_at = None
