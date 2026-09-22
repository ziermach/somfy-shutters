"""Carries firings out (specs/003-shutter-automations/research.md §1, §6).

The planner says when; this decides what happens at that moment and records it.
`run_due(now)` takes the time as an argument and does all the work, so tests drive
it with a fake clock. APScheduler only wakes it: one DateTrigger job, always set to
the earliest next firing over all rules.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .. import commands
from ..groups import Group, GroupStore
from ..models import utcnow
from .clock import ClockGuard, ClockVerdict
from .models import Firing, FiringStatus, Outcome, Rule, RuleDraft, status_from
from .planner import NextFiring, SunLookup, days_without_sun, firings_between, next_firing
from .store import AutomationStore
from .sun import sun_lookup
from .targets import Resolution, resolve

log = logging.getLogger(__name__)

GRACE = timedelta(minutes=10)
"""FR-012: a firing this late is still carried out; later, it is recorded as missed."""

CATCH_UP_LIMIT = timedelta(days=7)
"""How far back a restart looks. A Pi in a drawer for a month should not write a
thousand rows on its first boot."""

RETENTION = timedelta(days=90)
JOB_ID = "automation-wake"

PAUSE_KEY = "automation.pause"
HEARTBEAT_KEY = "automation.heartbeat"
LOCATION_KEY = "location"


@dataclass(frozen=True)
class Pause:
    paused: bool
    until: datetime | None = None


class AutomationEngine:
    def __init__(
        self,
        store: AutomationStore,
        state: Any,
        publish: Callable[[dict[str, Any]], Awaitable[None]],
        guard: ClockGuard | None = None,
        clock: Callable[[], datetime] = utcnow,
        scheduler: Any = None,
        groups: GroupStore | None = None,
    ) -> None:
        self.store = store
        self.groups = groups
        self.state = state
        self.publish = publish
        self.guard = guard or ClockGuard()
        self.clock = clock
        self.scheduler = scheduler
        self.started_at = clock()
        self.verdict = ClockVerdict(True)

    # --- context -------------------------------------------------------------

    @property
    def settings(self) -> Any:
        return self.state.tracker.settings

    @property
    def tz(self) -> Any:
        return self.settings.general.tz

    def location(self) -> dict[str, float] | None:
        return self.store.setting(LOCATION_KEY)

    def sun(self) -> SunLookup | None:
        where = self.location()
        if where is None:
            return None
        return sun_lookup(where["latitude"], where["longitude"], self.tz)

    def current_groups(self) -> list[Group]:
        return self.groups.groups() if self.groups is not None else []

    def targets(self, rule: RuleDraft) -> Resolution:
        """Who the rule reaches right now: groups resolved at this moment (feature 004)."""
        return resolve(rule.targets, list(self.settings.shutters), self.current_groups())

    def next_for(self, rule: Rule, now: datetime | None = None) -> NextFiring:
        return next_firing(
            rule,
            now or self.clock(),
            self.tz,
            self.sun(),
            has_targets=bool(self.targets(rule).reached),
        )

    def pause(self, now: datetime | None = None) -> Pause:
        raw = self.store.setting(PAUSE_KEY)
        if raw is None:
            return Pause(False)
        until = datetime.fromisoformat(raw["until"]) if raw.get("until") else None
        if until is not None and until <= (now or self.clock()):
            self.store.set_setting(PAUSE_KEY, None)  # expired: resume by itself
            return Pause(False)
        return Pause(True, until)

    def heartbeat(self) -> datetime | None:
        raw = self.store.setting(HEARTBEAT_KEY)
        return datetime.fromisoformat(raw) if raw else None

    # --- the clock -----------------------------------------------------------

    async def check_clock(self, now: datetime | None = None) -> ClockVerdict:
        """Re-evaluate the clock. Turning reliable triggers a catch-up."""
        now = now or self.clock()
        before = self.verdict
        self.verdict = self.guard.check(now, self.heartbeat())
        if self.verdict != before:
            log.info("clock %s", "reliable" if self.verdict.reliable else self.verdict.reason)
            await self.announce_state(now)
            if self.verdict.reliable:
                await self.catch_up(now)
            self.reschedule(now)
        return self.verdict

    def beat(self, now: datetime | None = None) -> None:
        """Written only while the clock is trusted: it is what 'went backwards' compares to."""
        if self.verdict.reliable:
            self.store.set_setting(HEARTBEAT_KEY, (now or self.clock()).isoformat())

    def state_json(self, now: datetime | None = None) -> dict[str, Any]:
        pause = self.pause(now)
        return {
            "paused": pause.paused,
            "until": pause.until.astimezone(self.tz).isoformat() if pause.until else None,
            "clock_reliable": self.verdict.reliable,
            "clock_reason": self.verdict.reason,
        }

    async def announce_state(self, now: datetime | None = None) -> None:
        await self.publish({"type": "automations", **self.state_json(now)})

    # --- firing --------------------------------------------------------------

    def _due(self, start: datetime, end: datetime) -> list[tuple[datetime, Rule]]:
        sun = self.sun()
        due = []
        for rule in self.store.rules():
            if not rule.enabled:
                continue
            reach = self.targets(rule)
            if not reach.reached and not reach.removed:
                # Its last group was deleted (feature 004, FR-026). It says "no_targets"
                # and does not fire; a firing of nothing would read as a failure.
                continue
            for planned in firings_between(rule, start, end, self.tz, sun):
                if not self.store.has_firing(rule.id, planned):
                    due.append((planned, rule))
        # FR-011: by planned time, then the order the rules were created.
        due.sort(key=lambda item: (item[0], item[1].created_at, item[1].id))
        return due

    async def run_due(self, now: datetime | None = None) -> list[Firing]:
        """Carry out every unrecorded firing of the last GRACE, in FR-011 order."""
        now = now or self.clock()
        if not self.verdict.reliable:
            return []  # catch_up records these once the clock can be trusted again
        done = []
        for planned, rule in self._due(now - GRACE, now):
            firing = await self._fire(rule, planned, now)
            if firing is not None:
                done.append(firing)
        await self._record_days_without_sun(now)
        return done

    async def _fire(self, rule: Rule, planned: datetime, now: datetime) -> Firing | None:
        # Recorded first: whatever happens next, this instant is never fired twice.
        provisional = Firing(rule_id=rule.id, planned_at=planned, status=FiringStatus.FIRED)
        if not self.store.record_firing(provisional):
            return None

        if self.pause(now).paused:
            firing = provisional.model_copy(update={"status": FiringStatus.PAUSED})
        elif rule.skip_planned_at is not None and rule.skip_planned_at == planned:
            self.store.set_skip(rule.id, None)
            firing = provisional.model_copy(update={"status": FiringStatus.SKIPPED})
        else:
            outcomes = await self._command(rule)
            firing = provisional.model_copy(
                update={"fired_at": now, "status": status_from(outcomes), "outcomes": outcomes}
            )
        self.store.finish_firing(firing)
        log.info("rule %s (%s) at %s: %s", rule.name, rule.id, planned, firing.status.value)
        await self._announce(rule, firing)
        return firing

    async def _command(self, rule: Rule) -> list[Outcome]:
        resolution = self.targets(rule)
        outcomes = []
        # FR-010: not retried, not queued. A shutter that could not be commanded
        # was not commanded. Each is commanded once, however many targets reach it.
        for result in await commands.apply_many(
            self.state, resolution.reached, rule.action.kind, rule.action.percent
        ):
            via = resolution.via.get(result["id"], [])
            if result["accepted"]:
                outcomes.append(Outcome(shutter_id=result["id"], result="commanded", via=via))
            elif result["error"] == "measurement_in_progress":
                outcomes.append(
                    Outcome(
                        shutter_id=result["id"], result="skipped", reason=result["error"], via=via
                    )
                )
            else:
                outcomes.append(
                    Outcome(
                        shutter_id=result["id"], result="failed", reason=result["error"], via=via
                    )
                )
        outcomes.extend(
            Outcome(shutter_id=sid, result="skipped", reason="removed")
            for sid in resolution.removed
        )
        return outcomes

    async def _record_days_without_sun(self, now: datetime) -> None:
        """A selected day whose sun event does not happen gets one no_sun record, at
        local midnight of that day, so it shows in the history instead of vanishing."""
        sun = self.sun()
        if sun is None:
            return
        today = now.astimezone(self.tz).replace(hour=0, minute=0, second=0, microsecond=0)
        for rule in self.store.rules():
            if not rule.enabled:
                continue
            for day in days_without_sun(rule, today, today, self.tz, sun):
                midnight = datetime(day.year, day.month, day.day, tzinfo=self.tz)
                record = Firing(rule_id=rule.id, planned_at=midnight, status=FiringStatus.NO_SUN)
                if self.store.record_firing(record):
                    await self._announce(rule, record)

    async def _announce(self, rule: Rule, firing: Firing) -> None:
        await self.publish(
            {
                "type": "automation_fired",
                "rule_id": rule.id,
                "rule_name": rule.name,
                "planned_at": firing.planned_at.astimezone(self.tz).isoformat(),
                "status": firing.status.value,
                "commanded": firing.commanded,
                "total": len(firing.outcomes),
            }
        )

    # --- restarts ------------------------------------------------------------

    async def catch_up(self, now: datetime | None = None) -> list[Firing]:
        """After a restart, or once the clock can be trusted again (research §6).

        Firings older than GRACE since the last heartbeat are recorded, not carried
        out: missed if the system was not running, held if it was and the clock
        was the reason. Newer ones are left to run_due, which carries them out.
        """
        now = now or self.clock()
        heartbeat = self.heartbeat()
        recorded = []
        if heartbeat is not None:
            start = max(heartbeat, now - CATCH_UP_LIMIT)
            for planned, rule in self._due(start, now - GRACE):
                status = FiringStatus.MISSED if planned < self.started_at else FiringStatus.HELD
                firing = Firing(rule_id=rule.id, planned_at=planned, status=status)
                if self.store.record_firing(firing):
                    await self._announce(rule, firing)
                    recorded.append(firing)
        recorded.extend(await self.run_due(now))
        self.beat(now)
        return recorded

    # --- scheduling ----------------------------------------------------------

    def earliest_next(self, now: datetime | None = None) -> datetime | None:
        now = now or self.clock()
        times = [
            nxt.at
            for rule in self.store.rules()
            if (nxt := self.next_for(rule, now)).at is not None
        ]
        return min(times) if times else None

    def reschedule(self, now: datetime | None = None) -> datetime | None:
        """Point the one timer at the earliest next firing, or remove it."""
        now = now or self.clock()
        at = self.earliest_next(now) if self.verdict.reliable else None
        if self.scheduler is not None:
            if self.scheduler.get_job(JOB_ID) is not None:
                self.scheduler.remove_job(JOB_ID)
            if at is not None:
                self.scheduler.add_job(
                    self._wake,
                    "date",
                    run_date=at,
                    id=JOB_ID,
                    misfire_grace_time=int(GRACE.total_seconds()),
                )
        return at

    async def _wake(self) -> None:
        now = self.clock()
        try:
            await self.run_due(now)
        finally:
            self.reschedule(now)

    def purge(self, now: datetime | None = None) -> int:
        return self.store.purge_before((now or self.clock()) - RETENTION)
