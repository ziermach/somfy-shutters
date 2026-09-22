"""The household's shutters, and what the bridge announces beyond them (feature 005).

Pi-Somfy announces every shutter it knows under its discovery topics. A shutter it
announces is not yet part of the household: it is *new* until a person confirms it
with a name. Confirming and removing mutate ``settings.shutter`` in place — the one
list every part of the app reads through ``settings.shutters`` / ``by_address`` — so
no reader had to change (research §3).

States (research §5): *new* (announced, not confirmed, not set aside), *active* (in
the household, from shutters.toml or the table), *set aside* (removed by a person
while the bridge still announces it), *forgotten* (active, but not re-announced
after the bridge's last restart).
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from .bridge.base import Report
from .config import Settings, ShutterConfig
from .roster_store import RosterStore, clean_name

log = logging.getLogger(__name__)

Origin = Literal["config", "bridge"]

WINDOW_SECONDS = 30.0
"""After the bridge comes online, how long its live announcements may take (research §2).
Pi-Somfy announces everything at once on connect; FR-017 allows 60 s in all."""

_TRANSLITERATION = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


class NotAnnounced(LookupError):
    """The address is not currently a new shutter."""


class NameTaken(ValueError):
    """Another household shutter already has this name."""


class ConfiguredByHand(RuntimeError):
    """The shutter lives in shutters.toml, which the app never writes."""


class MeasurementInProgress(RuntimeError):
    """A calibration run on this shutter is under way (FR-014)."""


@dataclass(frozen=True)
class Announcement:
    address: str
    name: str
    web_url: str | None
    retained: bool


@dataclass(frozen=True)
class ActiveEntry:
    id: str
    name: str
    address: str
    origin: Origin
    forgotten: bool


@dataclass(frozen=True)
class SetAside:
    address: str
    name: str


def slug(name: str, taken: set[str]) -> str:
    """An id from a name: ``[a-z0-9-]``, umlauts transliterated, unique by suffix.

    Fixed at confirmation. A later rename changes the name only — groups, rules,
    calibration and history key on the id.
    """
    text = name.strip().lower().translate(_TRANSLITERATION)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "rolladen"
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


class Roster:
    def __init__(
        self,
        settings: Settings,
        rows: RosterStore,
        *,
        publish: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        window_seconds: float = WINDOW_SECONDS,
    ) -> None:
        self.settings = settings
        self.rows = rows
        self.publish = publish
        # The app's state, set once it exists: removal reaches the tracker, groups,
        # rules and calibration through it. None in unit tests.
        self.state: Any = None
        self.config_ids = {s.id for s in settings.shutter}
        self.announced: dict[str, Announcement] = {}
        self.announcements_seen = False
        self._announced_web_url: str | None = None
        self.forgotten: set[str] = set()
        # The window after each bridge `online` (research §2). None while closed.
        self.window_seconds = window_seconds
        self._live_since_online: set[str] | None = None
        self._online: bool | None = None
        self._timer: asyncio.TimerHandle | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._build()

    def _build(self) -> None:
        """Hand-configured shutters first, unchanged; then the confirmed ones."""
        addresses = {s.address for s in self.settings.shutter}
        for row in self.rows.all():
            if row.state != "active":
                continue
            if row.address in addresses or row.id in self.config_ids:
                log.warning(
                    "shutter %s (%s) is in shutters.toml too; the file wins, the app's "
                    "entry is ignored",
                    row.id,
                    row.address,
                )
                continue
            self.settings.shutter.append(
                ShutterConfig(id=row.id, name=row.name, address=row.address)
            )
            addresses.add(row.address)

    # --- reading -------------------------------------------------------------

    def origin(self, shutter_id: str) -> Origin:
        return "config" if shutter_id in self.config_ids else "bridge"

    def is_forgotten(self, shutter_id: str) -> bool:
        return shutter_id in self.forgotten

    def active(self) -> list[ActiveEntry]:
        return [
            ActiveEntry(
                id=s.id,
                name=s.name,
                address=s.address,
                origin=self.origin(s.id),
                forgotten=s.id in self.forgotten,
            )
            for s in self.settings.shutter
        ]

    def set_aside(self) -> list[SetAside]:
        return [SetAside(r.address, r.name) for r in self.rows.all() if r.state == "set_aside"]

    def new(self) -> list[Announcement]:
        """Announced, not in the household, not set aside (FR-002)."""
        known = {s.address for s in self.settings.shutter}
        known |= {r.address for r in self.rows.all()}
        return sorted(
            (a for a in self.announced.values() if a.address not in known),
            key=lambda a: a.address,
        )

    @property
    def web_url(self) -> str | None:
        """The configured link wins over the announced one."""
        return self.settings.bridge.web_url or self._announced_web_url

    def still_announced(self, address: str) -> bool:
        return address in self.announced

    def name_in_use(self, name: str, except_id: str | None = None) -> bool:
        wanted = name.strip().casefold()
        return any(s.name.casefold() == wanted and s.id != except_id for s in self.settings.shutter)

    def unique_name(self, name: str) -> str:
        """The bridge's name, made unique for the prefilled field ("Küche" → "Küche 2")."""
        base = name.strip()[:37] or "Rolladen"
        candidate, n = base, 2
        while self.name_in_use(candidate):
            candidate, n = f"{base} {n}", n + 1
        return candidate

    def wire(self) -> dict[str, Any]:
        """GET /api/roster (contracts/rest.md)."""
        return {
            "active": [
                {
                    "id": e.id,
                    "name": e.name,
                    "address": e.address,
                    "origin": e.origin,
                    "forgotten": e.forgotten,
                    "removable": e.origin == "bridge",
                }
                for e in self.active()
            ],
            "new": [
                {
                    "address": a.address,
                    "bridge_name": a.name,
                    "suggested_name": self.unique_name(a.name),
                }
                for a in self.new()
            ],
            "set_aside": [{"address": s.address, "name": s.name} for s in self.set_aside()],
            "bridge": {"announcements_seen": self.announcements_seen, "web_url": self.web_url},
        }

    def _signature(self) -> tuple[Any, ...]:
        return (
            tuple((a.address, a.name) for a in self.new()),
            tuple(sorted(self.forgotten)),
        )

    async def _changed(self, *, household: bool = False) -> None:
        """Tell every client. ``household`` when the list of shutters itself changed,
        which makes the server send everyone a fresh snapshot (research §9)."""
        if self.publish is not None:
            await self.publish(
                {
                    "type": "roster",
                    "new": len(self.new()),
                    "forgotten": sorted(self.forgotten),
                    "household": household,
                }
            )

    # --- announcements -------------------------------------------------------

    async def handle(self, report: Report) -> None:
        before = self._signature()
        if not report.retained and report.name is not None:
            # A live announcement: the bridge knows this shutter now.
            if self._live_since_online is not None:
                self._live_since_online.add(report.address)
            shutter = self.settings.by_address(report.address)
            if shutter is not None:
                self.forgotten.discard(shutter.id)
        if report.name is None:
            self.announced.pop(report.address, None)
        else:
            self.announcements_seen = True
            if report.web_url:
                self._announced_web_url = report.web_url
            self.announced[report.address] = Announcement(
                report.address, report.name, report.web_url, report.retained
            )
        if self._signature() != before:
            await self._changed()

    # --- the bridge forgetting (US4) -----------------------------------------

    def bridge_availability(self, online: bool) -> None:
        """Called on every change of the bridge's reachability.

        Each transition to online opens the window in which the bridge announces, live,
        every shutter it still knows. Going offline decides nothing (FR-018).
        """
        if online and self._online is not True:
            self._live_since_online = set()
            self._cancel_timer()
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                self._timer = loop.call_later(self.window_seconds, self._window_elapsed)
        elif not online:
            self._cancel_timer()
            self._live_since_online = None
        self._online = online

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _window_elapsed(self) -> None:
        self._timer = None
        task = asyncio.create_task(self.close_window())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def close_window(self) -> None:
        """Decide who the bridge forgot: bridge shutters not announced live in the window.

        A window without a single live announcement decides nothing. That is what the
        app sees when it connects to a bridge that has been up for hours — only old
        news — and also a bridge with announcements switched off. Erring towards
        "still known" is deliberate: a forgotten mark disables a working shutter.
        """
        live = self._live_since_online
        self._live_since_online = None
        self._cancel_timer()
        if not live:
            return
        before = self._signature()
        for entry in self.active():
            if entry.origin == "bridge" and entry.address not in live:
                self.forgotten.add(entry.id)
        if self._signature() != before:
            log.warning("the bridge no longer announces: %s", ", ".join(sorted(self.forgotten)))
            await self._changed()

    # --- confirming and renaming ---------------------------------------------

    async def confirm(self, address: str, name: str) -> ShutterConfig:
        address = address.strip().lower()
        if address not in {a.address for a in self.new()}:
            raise NotAnnounced(address)
        name = clean_name(name)
        if self.name_in_use(name):
            raise NameTaken(name)
        taken = set(self.settings.shutters) | {r.id for r in self.rows.all()}
        shutter_id = slug(name, taken)
        self.rows.insert(shutter_id, address, name)
        shutter = ShutterConfig(id=shutter_id, name=name, address=address)
        self.settings.shutter.append(shutter)
        if self.state is not None:
            self.state.tracker.add_shutter(shutter)
        log.info("shutter %s (%s) joined the household", shutter_id, address)
        await self._changed(household=True)
        return shutter

    async def rename(self, shutter_id: str, name: str) -> ShutterConfig:
        if shutter_id not in self.settings.shutters:
            raise KeyError(shutter_id)
        if self.origin(shutter_id) == "config":
            raise ConfiguredByHand(shutter_id)
        name = clean_name(name)
        if self.name_in_use(name, except_id=shutter_id):
            raise NameTaken(name)
        self.rows.rename(shutter_id, name)
        index = next(i for i, s in enumerate(self.settings.shutter) if s.id == shutter_id)
        renamed = self.settings.shutter[index].model_copy(update={"name": name})
        self.settings.shutter[index] = renamed
        await self._changed(household=True)
        return renamed

    # --- removing and restoring ----------------------------------------------

    def _refusal(self, shutter_id: str) -> str | None:
        if self.origin(shutter_id) == "config":
            return "configured_by_hand"
        runs = getattr(self.state, "runs", None)
        if runs is not None and runs.is_measuring(shutter_id):
            return "measurement_in_progress"
        return None

    def removal_preview(self, shutter_id: str) -> dict[str, Any]:
        """What removing would take with it, named, before anyone confirms (FR-012)."""
        if shutter_id not in self.settings.shutters:
            raise KeyError(shutter_id)
        state = self.state
        groups = getattr(state, "groups", None)
        engine = getattr(state, "automation", None)
        tracker = getattr(state, "tracker", None)
        address = self.settings.shutters[shutter_id].address
        reason = self._refusal(shutter_id)
        return {
            "removable": reason is None,
            "groups": [
                {"id": g.id, "name": g.name}
                for g in (groups.groups() if groups else [])
                if shutter_id in g.members
            ],
            "rules": [
                {
                    "id": r.id,
                    "name": r.name,
                    "left_without_target": r.targets.shutters == [shutter_id]  # type: ignore[union-attr]
                    and not r.targets.groups,  # type: ignore[union-attr]
                }
                for r in (engine.store.rules_naming(shutter_id) if engine else [])
            ],
            "calibrated": bool(tracker and tracker.is_calibrated(shutter_id)),
            "still_announced": self.still_announced(address),
            "reason": reason,
        }

    async def remove(self, shutter_id: str) -> bool:
        """Take a shutter out of the household. Returns whether it was set aside.

        Sends nothing to the bridge (FR-015): a travel under way finishes on its own.
        Cascades through everything that names the shutter (data-model.md), in an
        order where an interruption leaves nothing pointing at a shutter that is gone.
        """
        if shutter_id not in self.settings.shutters:
            raise KeyError(shutter_id)
        reason = self._refusal(shutter_id)
        if reason == "configured_by_hand":
            raise ConfiguredByHand(shutter_id)
        if reason == "measurement_in_progress":
            raise MeasurementInProgress(shutter_id)
        address = self.settings.shutters[shutter_id].address
        state = self.state
        remaining = [s for s in self.settings.shutters if s != shutter_id]
        if state is not None:
            groups = getattr(state, "groups", None)
            if groups is not None and groups.prune(remaining):
                await self._publish(
                    {"type": "groups", "groups": [g.wire() for g in groups.groups()]}
                )
            engine = getattr(state, "automation", None)
            if engine is not None:
                named = engine.store.rules_naming(shutter_id)
                engine.store.remove_shutter(shutter_id)
                if named:
                    engine.reschedule()
                    await self._publish({"type": "rules_changed"})
            calibration = getattr(state, "calibration", None)
            if calibration is not None:
                calibration.clear(shutter_id)
            getattr(state, "pending_confirmations", {}).pop(shutter_id, None)
            getattr(state, "pending_checks", {}).pop(shutter_id, None)
            state.store.delete(shutter_id)
            state.tracker.remove_shutter(shutter_id)
        self.settings.shutter[:] = [s for s in self.settings.shutter if s.id != shutter_id]
        self.forgotten.discard(shutter_id)
        set_aside = self.still_announced(address)
        if set_aside:
            # Still announced: kept aside, so it does not come back as "new" (FR-016).
            self.rows.set_state(shutter_id, "set_aside")
        else:
            self.rows.delete(shutter_id)
        log.info(
            "shutter %s (%s) left the household, set aside: %s", shutter_id, address, set_aside
        )
        await self._changed(household=True)
        return set_aside

    async def restore(self, address: str) -> None:
        """A set-aside shutter becomes new again, to be confirmed with a name."""
        row = self.rows.by_address(address)
        if row is None or row.state != "set_aside":
            raise KeyError(address)
        self.rows.delete(row.id)
        await self._changed()

    async def _publish(self, event: dict[str, Any]) -> None:
        if self.publish is not None:
            await self.publish(event)
