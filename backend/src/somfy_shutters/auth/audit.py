"""The record of who did what (specs/007-api-auth-audit/research.md §9).

Ordered by its own id, never by wall time: a Pi without a battery-backed clock can
boot hours in the past, and the record must not reorder itself when the network
corrects it. Writing never raises — a shutter must move even if the ledger cannot
be written (FR-020); the failure goes to the log instead.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import utcnow
from .models import Actor

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_entry (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    at            TEXT NOT NULL,
    clock_ok      INTEGER NOT NULL,
    actor_kind    TEXT NOT NULL,
    actor_id      TEXT,
    actor_name    TEXT,
    action        TEXT NOT NULL,
    shutter_id    TEXT,
    target        TEXT,
    outcome       TEXT NOT NULL,
    detail        TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS audit_entry_shutter ON audit_entry (shutter_id, id);
CREATE INDEX IF NOT EXISTS audit_entry_actor   ON audit_entry (actor_id, id);
CREATE INDEX IF NOT EXISTS audit_entry_at      ON audit_entry (at);
"""

MAX_PAGE = 200


@dataclass(frozen=True)
class Entry:
    id: int
    at: datetime
    clock_ok: bool
    actor: Actor
    action: str
    shutter_id: str | None
    target: str | None
    outcome: str
    detail: dict[str, Any]


class AuditLog:
    def __init__(self, db_path: str | Path, clock: Callable[[], datetime] = utcnow) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            db_path, isolation_level=None, check_same_thread=False, timeout=10
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            # WAL: the record is read while commands are written (research §9).
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def record(
        self,
        actor: Actor,
        action: str,
        outcome: str,
        *,
        shutter_id: str | None = None,
        target: str | None = None,
        detail: dict[str, Any] | None = None,
        clock_ok: bool = True,
    ) -> None:
        """Never raises."""
        try:
            with self._lock:
                self._conn.execute(
                    """
                    INSERT INTO audit_entry
                        (at, clock_ok, actor_kind, actor_id, actor_name, action,
                         shutter_id, target, outcome, detail)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.clock().isoformat(),
                        int(clock_ok),
                        actor.kind,
                        actor.id,
                        actor.name,
                        action,
                        shutter_id,
                        target,
                        outcome,
                        json.dumps(detail or {}),
                    ),
                )
        except Exception:
            log.exception("could not record %s by %s (%s)", action, actor.kind, outcome)

    @staticmethod
    def _entry(row: sqlite3.Row) -> Entry:
        return Entry(
            id=row["id"],
            at=datetime.fromisoformat(row["at"]),
            clock_ok=bool(row["clock_ok"]),
            actor=Actor(row["actor_kind"], row["actor_id"], row["actor_name"]),
            action=row["action"],
            shutter_id=row["shutter_id"],
            target=row["target"],
            outcome=row["outcome"],
            detail=json.loads(row["detail"]),
        )

    def query(
        self,
        *,
        shutter: str | None = None,
        actor: str | None = None,
        before: int | None = None,
        limit: int = 50,
    ) -> list[Entry]:
        """Newest first. `before` is an entry id, for paging."""
        clauses, params = [], []
        if shutter is not None:
            clauses.append("shutter_id = ?")
            params.append(shutter)
        if actor is not None:
            clauses.append("actor_id = ?")
            params.append(actor)
        if before is not None:
            clauses.append("id < ?")
            params.append(before)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, MAX_PAGE)))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM audit_entry {where} ORDER BY id DESC LIMIT ?", params
            ).fetchall()
        return [self._entry(r) for r in rows]

    def purge(self, older_than: datetime) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM audit_entry WHERE at < ?", (older_than.isoformat(),)
            )
        return cursor.rowcount
