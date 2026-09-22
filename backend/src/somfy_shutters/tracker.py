"""Where a shutter is, and how much that can be trusted.

No I/O lives here: the tracker takes commands and reports, returns state, and
announces what happened on an event bus. That is what makes the rules below
testable without a broker, a socket or a real clock.

The hard part is :meth:`Tracker.handle_report`. A position from Pi-Somfy is not a
measurement — it is Pi-Somfy's own dead reckoning from its own configured travel
time. Precedence therefore goes to whoever knows more about what *caused* the
movement, not to whoever spoke last. See research.md, section 5.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from .bridge.base import Report
from .calibration import to_level, to_percent
from .config import Settings
from .models import (
    Action,
    Confidence,
    Direction,
    Movement,
    Origin,
    PositionEstimate,
    Source,
    utcnow,
)
from .store import Store

log = logging.getLogger(__name__)

IGNORE_DELTA = 3
"""Two estimates within 3 pp are noise. Moving the graphic would be churn."""

EXTERNAL_WINDOW = 3.0
"""Reports this close together, while we are idle, mean somebody else is driving."""

EXTERNAL_MIN_DELTA = 2
"""How far consecutive reports must move before we call it a real movement."""

CORRECTION_EASE_MS = 400

BRIDGE_RUN_SLACK = 1.5
"""How much longer than our full travel time the bridge may take for one command
before its reports stop counting as that command."""

BRIDGE_RUN_TOLERANCE = 2
"""Level points either side of the bridge's run that still count as on the way."""


class UnknownShutter(KeyError):
    pass


class Tracker:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        *,
        emit: Callable[[dict], Awaitable[None]],
        monotonic: Callable[[], float] = time.monotonic,
        clock: Callable[[], datetime] = utcnow,
        calibration: object | None = None,
    ) -> None:
        self._settings = settings
        # Feature 002. Absent, the tracker behaves exactly as feature 001 did:
        # configured value or default, and a linear travel.
        self._calibration = calibration
        self._store = store
        self._emit = emit
        self._monotonic = monotonic
        self._clock = clock

        restored = store.load_all()
        self._positions: dict[str, PositionEstimate] = {
            sid: restored.get(sid, PositionEstimate.unknown()) for sid in settings.shutters
        }
        self._movements: dict[str, Movement] = {}
        self._last_report: dict[str, tuple[int, float]] = {}
        # Which way a shutter last went. A report is in the bridge's level
        # coordinate and needs a curve to become a percentage; the direction it
        # last travelled is the one that put it where it is.
        self._last_direction: dict[str, Direction] = {}
        # What the bridge's own counter says, as far as we can tell: the level we
        # last sent once the travel finished, a halt, or a report. Commands are
        # sent relative to it, because the bridge runs the motor for the
        # difference between its counter and the new level — not for the
        # distance the curve of the new direction would compute.
        self._bridge_level: dict[str, float] = {
            # After a restart the best guess is the stored position. Exact at the
            # end stops, where Pi-Somfy's counter is reset too.
            sid: to_level(position.percent, self._curve_a(sid, Direction.UP))
            for sid, position in self._positions.items()
            if position.percent is not None
        }
        # The bridge's own run for our last command: counter at the start, level
        # sent, and when it must be over. Its reports along that way are it doing
        # what we asked, on its own clock — not somebody else moving the shutter.
        self._bridge_runs: dict[str, tuple[float, float, float]] = {}
        # Shutters the bridge says are moving on somebody else's command — a physical
        # remote it heard (feature 006). Transient: a restart forgets it.
        self._external_moving: set[str] = set()

    # --- reading -------------------------------------------------------------

    @property
    def settings(self) -> Settings:
        return self._settings

    def position(self, shutter_id: str) -> PositionEstimate:
        self._require(shutter_id)
        movement = self._movements.get(shutter_id)
        if movement is None:
            return self._positions[shutter_id]
        # While travelling the live value is interpolated; the stored one is where
        # it started. Clients animate themselves, this is for late joiners.
        # The curve bends the middle of the travel and leaves the ends exact,
        # so a verified shutter still arrives at 0 % and 100 % on the dot.
        return PositionEstimate(
            percent=movement.position_at(self._monotonic()),
            confidence=Confidence.ESTIMATED,
            certain_at=self._positions[shutter_id].certain_at,
            source=Source.COMMAND,
        )

    def movement(self, shutter_id: str) -> Movement | None:
        return self._movements.get(shutter_id)

    def _travel_seconds(self, shutter_id: str, direction: Direction) -> float:
        """Manual value, else measured, else the default (feature 002)."""
        if self._calibration is not None:
            return self._calibration.travel_seconds(shutter_id, direction)
        return self._settings.travel_seconds(shutter_id, direction.value)

    def is_calibrated(self, shutter_id: str) -> bool:
        """Both directions have a real travel time — typed in or measured.

        Feature 001 only knew typed-in values; a shutter measured with feature 002
        read "Laufzeit nicht gemessen" on the overview while the calibration screen
        said "gemessen, 6 Läufe".
        """
        if self._calibration is None:
            return self._settings.shutters[shutter_id].calibrated
        return all(
            self._calibration.effective(shutter_id, d).source != "default"
            for d in (Direction.UP, Direction.DOWN)
        )

    def _curve_a(self, shutter_id: str, direction: Direction) -> float:
        """The verification shape. One means the linear travel of feature 001."""
        if self._calibration is not None:
            return self._calibration.curve_a(shutter_id, direction)
        return 1.0

    def _require(self, shutter_id: str) -> None:
        if shutter_id not in self._settings.shutters:
            raise UnknownShutter(shutter_id)

    # --- commanding ----------------------------------------------------------

    def plan(
        self, shutter_id: str, action: Action, target_percent: int | None = None
    ) -> int | None:
        """What position this action asks for, or None when it is a stop."""
        self._require(shutter_id)
        if action is Action.OPEN:
            return 100
        if action is Action.CLOSE:
            return 0
        if action is Action.POSITION:
            if target_percent is None:
                raise ValueError("action 'position' requires target_percent")
            return target_percent
        return None

    async def start_movement(
        self, shutter_id: str, target: int, level: int | None = None
    ) -> Movement | None:
        """Begin travel. Returns None when the shutter is already there.

        `level` is what was sent to the bridge; the caller asks level_for()
        first, so that nothing is recorded when the bridge refuses the send.
        """
        self._require(shutter_id)
        if level is None:
            level = self.level_for(shutter_id, target)
        bridge_from = self.bridge_level(shutter_id)
        current = self.position(shutter_id)
        # An unknown position still has to be drivable — that is how it becomes
        # known again. Assume the far end so the travel time is not underestimated.
        from_percent = (
            current.percent if current.percent is not None else (0 if target == 100 else 100)
        )
        if from_percent == target:
            return None

        direction = Direction.UP if target > from_percent else Direction.DOWN
        full_travel = self._travel_seconds(shutter_id, direction)
        curve_a = self._curve_a(shutter_id, direction)
        # The motor runs on time, which is the level coordinate — so that is
        # where the distance has to be measured, not in percentages.
        start_level = to_level(from_percent, curve_a)
        end_level = to_level(target, curve_a)
        duration = full_travel * abs(end_level - start_level) / 100.0
        if bridge_from is None:
            # Nothing is known about the counter, so assume the far end, as for
            # an unknown position: the bridge may run the whole window.
            bridge_from = 0.0 if direction is Direction.UP else 100.0
            bridge_known = False
            # And the percentage came from the same guess. Animating a crawl from
            # an assumed 96 % to 100 % for a whole window's time is worse than
            # admitting the start is the far end.
            from_percent = 0 if direction is Direction.UP else 100
            start_level = to_level(from_percent, curve_a)
            duration = full_travel * abs(end_level - start_level) / 100.0
        else:
            bridge_known = True
        # The bridge times the motor on its own counter. Sent to an end stop from
        # a counter that lags, it keeps its timer running after the shutter has
        # hit the stop — and a command inside that window starts from a counter
        # that is wrong. The travel is over when both agree.
        duration = max(duration, full_travel * abs(level - bridge_from) / 100.0)
        started = self._clock()
        movement = Movement(
            shutter_id=shutter_id,
            from_percent=from_percent,
            target_percent=target,
            direction=direction,
            started_at=started,
            expected_arrival=started + timedelta(seconds=duration),
            origin=Origin.LOCAL,
            curve_a=curve_a,
            bridge_from=bridge_from,
            bridge_to=float(level),
            bridge_known=bridge_known,
            started_monotonic=self._monotonic(),
            duration_seconds=duration,
        )
        self._movements[shutter_id] = movement
        self._last_direction[shutter_id] = direction
        # The bridge may well run longer than we do: its travel time is its own,
        # and after an unknown start its counter and ours need not agree. Long
        # enough for a whole window, with room for a slow bridge.
        self._bridge_runs[shutter_id] = (
            bridge_from,
            float(level),
            movement.started_monotonic + full_travel * BRIDGE_RUN_SLACK + 2.0,
        )
        # Recorded now, so an interruption mid-travel is recoverable as unknown.
        self._store.save(shutter_id, self._positions[shutter_id], was_moving=True, now=started)
        await self._emit({"type": "movement", "shutter_id": shutter_id, "movement": movement})
        return movement

    def last_direction(self, shutter_id: str) -> Direction | None:
        """Which way this shutter last travelled on our command, if we know."""
        return self._last_direction.get(shutter_id)

    def bridge_level(self, shutter_id: str) -> float | None:
        """The bridge's counter right now, if we have any idea of it."""
        movement = self._movements.get(shutter_id)
        if movement is not None:
            return movement.level_at(self._monotonic()) if movement.bridge_known else None
        return self._bridge_level.get(shutter_id)

    def level_for(self, shutter_id: str, target_percent: int) -> int:
        """What to ask the bridge for, so the shutter lands on `target_percent`.

        Everything the user and the API speak is a physical percentage. The
        bridge speaks time: it runs the motor for the difference between its
        own counter and the new level. So the level sent is that counter plus
        the distance, in this direction's time coordinate, still to travel. An
        absolute conversion was right only from an end stop — after a reversal
        mid-window the two sides disagreed about the distance, the app declared
        arrival while the motor was still running, and the next command landed
        in the middle of a travel.
        """
        self._require(shutter_id)
        if target_percent in (0, 100):
            # The motor stops at the end stop whatever the counter says, and the
            # counter is reset by it.
            return target_percent
        current = self.position(shutter_id).percent
        if current is None:
            direction = Direction.UP if target_percent == 100 else Direction.DOWN
        elif target_percent == current:
            # No travel, so the target says nothing about direction. The way it
            # last went is the curve that put it here.
            direction = self._last_direction.get(shutter_id, Direction.UP)
        else:
            direction = Direction.UP if target_percent > current else Direction.DOWN
        a = self._curve_a(shutter_id, direction)
        counter = self.bridge_level(shutter_id)
        if current is None or counter is None:
            return round(to_level(target_percent, a))
        level = counter + to_level(target_percent, a) - to_level(current, a)
        return round(max(0.0, min(100.0, level)))

    def halt_level(self, shutter_id: str) -> int:
        """What to send so the shutter stops where it is right now.

        While travelling this comes straight from the movement, in the level
        coordinate the motor actually runs in. Going through the displayed
        percentage would have to guess a direction, and "target == current"
        always guessed up — the wrong curve for a shutter on its way down.
        """
        self._require(shutter_id)
        counter = self.bridge_level(shutter_id)
        if counter is not None:
            return round(counter)
        current = self._positions[shutter_id].percent
        return self.level_for(shutter_id, current if current is not None else 0)

    def _report_direction(self, shutter_id: str, level: int) -> Direction:
        """Which curve a report has to be read through.

        During our own travel that is the travel's direction. While idle a report
        that moves the value was caused by something we did not command — a
        physical remote — and which side of our estimate it lands on says which
        way that went. Only with nothing to compare against does the last known
        direction decide, and after a restart there is not even that.
        """
        movement = self._movements.get(shutter_id)
        if movement is not None:
            return movement.direction
        previous = self._positions[shutter_id].percent
        if previous is not None:
            # Compared through the same curve on both sides, so the answer does
            # not depend on which curve is used for it.
            here = to_level(previous, self._curve_a(shutter_id, Direction.UP))
            if level > here + 0.5:
                return Direction.UP
            if level < here - 0.5:
                return Direction.DOWN
        return self._last_direction.get(shutter_id, Direction.UP)

    def forget_bridge_run(self, shutter_id: str) -> None:
        """For the simulator's injected reports, which stand for "this happened"
        rather than for the bridge still counting through our last command."""
        self._bridge_runs.pop(shutter_id, None)

    def _is_our_bridge_run(self, shutter_id: str, level: int) -> bool:
        run = self._bridge_runs.get(shutter_id)
        if run is None:
            return False
        start, end, deadline = run
        if self._monotonic() > deadline:
            del self._bridge_runs[shutter_id]
            return False
        low, high = min(start, end), max(start, end)
        if not low - BRIDGE_RUN_TOLERANCE <= level <= high + BRIDGE_RUN_TOLERANCE:
            return False
        if abs(level - end) <= BRIDGE_RUN_TOLERANCE:
            del self._bridge_runs[shutter_id]  # it has arrived at what we sent
        return True

    def percent_from_level(self, shutter_id: str, level: int) -> int:
        """A report arrives in the bridge's coordinate; this is what it means."""
        direction = self._report_direction(shutter_id, level)
        return round(to_percent(level, self._curve_a(shutter_id, direction)))

    async def stop(self, shutter_id: str) -> PositionEstimate:
        """Halt where it is — not at the original target (FR-016)."""
        self._require(shutter_id)
        movement = self._movements.pop(shutter_id, None)
        self._bridge_runs.pop(shutter_id, None)
        if movement is not None:
            if movement.bridge_known:
                self._bridge_level[shutter_id] = movement.level_at(self._monotonic())
            else:
                self._bridge_level.pop(shutter_id, None)
            percent = movement.position_at(self._monotonic())
            await self._settle(shutter_id, percent, Source.COMMAND)
        return self._positions[shutter_id]

    async def confirm_arrival(self, shutter_id: str, percent: int) -> PositionEstimate:
        """A person said the shutter has arrived.

        That is an observation, and a better one than our own timer: the timer
        is running on the travel time we are in the middle of measuring. Drop
        the movement and settle where they say it is.
        """
        self._require(shutter_id)
        self._movements.pop(shutter_id, None)
        await self._settle(shutter_id, percent, Source.COMMAND)
        return self._positions[shutter_id]

    async def tick(self) -> None:
        """Settle any movement that has arrived. Called by the app loop."""
        now = self._monotonic()
        for shutter_id, movement in list(self._movements.items()):
            if movement.is_done(now):
                del self._movements[shutter_id]
                if movement.bridge_to is not None:
                    self._bridge_level[shutter_id] = movement.bridge_to
                await self._settle(
                    shutter_id, movement.target_percent, Source.COMMAND, settled=movement
                )

    async def _settle(
        self,
        shutter_id: str,
        percent: int,
        source: Source,
        settled: Movement | None = None,
    ) -> None:
        previous = self._positions[shutter_id]
        if percent in (0, 100):
            self._bridge_level[shutter_id] = float(percent)
            position = PositionEstimate.at_end_stop(percent, source, self._clock())
        else:
            position = PositionEstimate(
                percent=percent,
                confidence=Confidence.ESTIMATED,
                # Leaving an end stop does not make the old certainty newer.
                certain_at=previous.certain_at,
                source=source,
            )
        self._positions[shutter_id] = position
        self._store.save(shutter_id, position, was_moving=False, now=self._clock())
        await self._emit(
            {
                "type": "position",
                "shutter_id": shutter_id,
                "position": position,
                # Present only when a movement ran to completion. Feature 002 uses
                # it to decide whether a travel is worth one question.
                "settled_movement": settled,
            }
        )

    # --- reports from the bridge (FR-017) ------------------------------------

    async def handle(self, report: Report) -> None:
        """Every kind of report from the bridge (feature 006).

        Live positions go through feature 001's reconciliation unchanged; retained
        positions and movement reports get their own rules.
        """
        if report.kind == "position" and report.percent is not None:
            if report.retained:
                await self._handle_retained_position(report.address, report.percent)
            else:
                await self.handle_report(report.address, report.percent)
        elif report.kind == "movement" and report.state is not None and not report.retained:
            await self._handle_movement(report.address, report.state)

    async def _handle_retained_position(self, address: str, level: int) -> None:
        """Old news from the broker's store, delivered on connect.

        It records the bridge's counter — feature 002's relative commands need it — and
        fills a position the app does not know. A position the app does know is left
        alone: its own record is newer than the broker's. And it is never "certain",
        not even at 0 or 100: it is the bridge's old belief, not an end stop observed now.
        """
        shutter = self._settings.by_address(address)
        if shutter is None:
            return
        shutter_id = shutter.id
        if shutter_id in self._movements:
            return
        self._bridge_level[shutter_id] = float(level)
        if self._positions[shutter_id].percent is not None:
            return
        await self._accept(
            shutter_id,
            PositionEstimate(
                percent=self.percent_from_level(shutter_id, level),
                confidence=Confidence.ESTIMATED,
                certain_at=None,
                source=Source.REPORT,
            ),
        )

    def _bridge_run_active(self, shutter_id: str) -> bool:
        run = self._bridge_runs.get(shutter_id)
        return run is not None and self._monotonic() <= run[2]

    async def _handle_movement(self, address: str, state: str) -> None:
        """The bridge says a shutter starts or stops moving (live only).

        An "opening"/"closing" we did not cause is a physical remote the bridge heard:
        from that moment the shutter is somebody else's, and the next positions are
        accepted as they come — no need to wait for two reports to guess it.
        """
        shutter = self._settings.by_address(address)
        if shutter is None:
            return
        shutter_id = shutter.id
        if state in ("opening", "closing"):
            if shutter_id in self._movements or self._bridge_run_active(shutter_id):
                return  # our own command, narrated back to us
            self._external_moving.add(shutter_id)
            previous = self._positions[shutter_id]
            await self._accept(
                shutter_id,
                PositionEstimate(
                    percent=previous.percent,
                    confidence=Confidence.ESTIMATED
                    if previous.percent is not None
                    else Confidence.UNKNOWN,
                    certain_at=self._clock(),
                    source=Source.REPORT,
                ),
            )
        else:
            self._external_moving.discard(shutter_id)

    async def handle_report(self, address: str, level: int) -> None:
        shutter = self._settings.by_address(address)
        if shutter is None:
            return  # logged once by the adapter
        shutter_id = shutter.id
        percent = self.percent_from_level(shutter_id, level)

        if shutter_id in self._movements:
            # We know exactly when we sent the command; the bridge's timer started
            # later and rounds. Our estimate wins, and the animation stays smooth.
            self._last_report[shutter_id] = (percent, self._monotonic())
            return

        # Idle, the report is the bridge's counter itself — the best reading of
        # it there is.
        self._bridge_level[shutter_id] = float(level)

        if self._is_our_bridge_run(shutter_id, level):
            # Our travel has ended by our clock, and the bridge is still working
            # through the same command. Taking these as corrections made the card
            # jump back and climb in one-second steps, and read the bridge's own
            # progress as a physical remote — refreshing a certainty nobody had.
            return
        previous = self._positions[shutter_id]
        last = self._last_report.get(shutter_id)
        now_mono = self._monotonic()
        self._last_report[shutter_id] = (percent, now_mono)

        if shutter_id in self._external_moving and percent not in (0, 100):
            # The bridge told us somebody else is driving: take the value as it
            # comes, freshly, without the noise filter or the two-report guess.
            await self._accept(
                shutter_id,
                PositionEstimate(
                    percent=percent,
                    confidence=Confidence.ESTIMATED,
                    certain_at=self._clock(),
                    source=Source.REPORT,
                ),
                corrected=True,
            )
            return

        if percent in (0, 100):
            # An end stop is mechanically true whoever reports it.
            await self._accept(
                shutter_id, PositionEstimate.at_end_stop(percent, Source.REPORT, self._clock())
            )
            return

        # Noise is filtered before anything else. Two reports 2 pp apart that both
        # sit within tolerance of what we believe are two estimates disagreeing
        # slightly, not somebody driving the shutter — checking for movement first
        # misreads that as a physical remote.
        if previous.percent is not None and abs(percent - previous.percent) <= IGNORE_DELTA:
            return

        external = (
            last is not None
            and now_mono - last[1] <= EXTERNAL_WINDOW
            and abs(percent - last[0]) >= EXTERNAL_MIN_DELTA
        )

        if external:
            # A physical remote was used. Pi-Somfy heard the command and we did
            # not, so its clock is fresher than ours — this is the one case where
            # a report legitimately refreshes the age.
            await self._accept(
                shutter_id,
                PositionEstimate(
                    percent=percent,
                    confidence=Confidence.ESTIMATED,
                    certain_at=self._clock(),
                    source=Source.REPORT,
                ),
                corrected=True,
            )
            return

        # The report wins, but taking a second estimate does not make the position
        # freshly known: certain_at is carried over untouched.
        await self._accept(
            shutter_id,
            PositionEstimate(
                percent=percent,
                confidence=Confidence.ESTIMATED,
                certain_at=previous.certain_at,
                source=Source.REPORT,
            ),
            corrected=True,
        )

    async def _accept(
        self, shutter_id: str, position: PositionEstimate, *, corrected: bool = False
    ) -> None:
        self._positions[shutter_id] = position
        self._store.save(shutter_id, position, was_moving=False, now=self._clock())
        event = {
            "type": "correction" if corrected else "position",
            "shutter_id": shutter_id,
            "position": position,
        }
        if corrected:
            event["ease_ms"] = CORRECTION_EASE_MS
            log.info("corrected %s to %s%% from a bridge report", shutter_id, position.percent)
        await self._emit(event)

    # --- derived -------------------------------------------------------------

    def is_stale(self, shutter_id: str) -> bool:
        return self.position(shutter_id).is_stale(
            self._settings.general.stale_after_hours, self._clock()
        )

    def nearest_end_stop(self, shutter_id: str) -> int:
        """For a resync. An unknown position cannot have a nearest one — pick open."""
        current = self.position(shutter_id)
        if current.percent is None:
            return 100
        return 100 if current.percent >= 50 else 0
