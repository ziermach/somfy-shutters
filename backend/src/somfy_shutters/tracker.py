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
        k = self._curve_k(shutter_id, movement.direction)
        return PositionEstimate(
            percent=movement.position_at(self._monotonic(), curve_k=k),
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

    def _curve_k(self, shutter_id: str, direction: Direction) -> float:
        """The verification shape. Zero means the linear travel of feature 001."""
        if self._calibration is not None:
            return self._calibration.curve_k(shutter_id, direction)
        return 0.0

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

    async def start_movement(self, shutter_id: str, target: int) -> Movement | None:
        """Begin travel. Returns None when the shutter is already there."""
        self._require(shutter_id)
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
        duration = full_travel * abs(target - from_percent) / 100.0
        started = self._clock()
        movement = Movement(
            shutter_id=shutter_id,
            from_percent=from_percent,
            target_percent=target,
            direction=direction,
            started_at=started,
            expected_arrival=started + timedelta(seconds=duration),
            origin=Origin.LOCAL,
            started_monotonic=self._monotonic(),
            duration_seconds=duration,
        )
        self._movements[shutter_id] = movement
        # Recorded now, so an interruption mid-travel is recoverable as unknown.
        self._store.save(shutter_id, self._positions[shutter_id], was_moving=True, now=started)
        await self._emit({"type": "movement", "shutter_id": shutter_id, "movement": movement})
        return movement

    async def stop(self, shutter_id: str) -> PositionEstimate:
        """Halt where it is — not at the original target (FR-016)."""
        self._require(shutter_id)
        movement = self._movements.pop(shutter_id, None)
        if movement is not None:
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
                await self._settle(shutter_id, movement.target_percent, Source.COMMAND)

    async def _settle(self, shutter_id: str, percent: int, source: Source) -> None:
        previous = self._positions[shutter_id]
        if percent in (0, 100):
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
        await self._emit({"type": "position", "shutter_id": shutter_id, "position": position})

    # --- reports from the bridge (FR-017) ------------------------------------

    async def handle_report(self, address: str, percent: int) -> None:
        shutter = self._settings.by_address(address)
        if shutter is None:
            return  # logged once by the adapter
        shutter_id = shutter.id

        if shutter_id in self._movements:
            # We know exactly when we sent the command; the bridge's timer started
            # later and rounds. Our estimate wins, and the animation stays smooth.
            self._last_report[shutter_id] = (percent, self._monotonic())
            return

        previous = self._positions[shutter_id]
        last = self._last_report.get(shutter_id)
        now_mono = self._monotonic()
        self._last_report[shutter_id] = (percent, now_mono)

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
