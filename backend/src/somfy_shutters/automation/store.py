"""Rules, firing records and a few settings, in the app's SQLite database.

The firing table is what makes double firing impossible: a firing is inserted
under UNIQUE(rule_id, planned_at) *before* any command goes out, so a restart, a
clock jump or a timer that wakes twice finds the row and does nothing.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..models import utcnow
from .models import Firing, FiringStatus, Outcome, Rule, RuleDraft

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS automation_rule (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    enabled         INTEGER NOT NULL,
    days            INTEGER NOT NULL,
    trigger         TEXT NOT NULL,
    targets         TEXT NOT NULL,
    action          TEXT NOT NULL,
    skip_planned_at TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS automation_firing (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id     TEXT NOT NULL REFERENCES automation_rule(id) ON DELETE CASCADE,
    planned_at  TEXT NOT NULL,
    fired_at    TEXT,
    status      TEXT NOT NULL,
    outcomes    TEXT NOT NULL DEFAULT '[]',
    UNIQUE (rule_id, planned_at)
);

CREATE INDEX IF NOT EXISTS automation_firing_planned ON automation_firing (planned_at);

CREATE TABLE IF NOT EXISTS app_setting (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _utc(at: datetime) -> str:
    """One spelling per instant: the dedupe key compares strings."""
    return at.astimezone(UTC).replace(microsecond=0).isoformat()


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _days_to_mask(days: list[bool]) -> int:
    return sum(1 << i for i, on in enumerate(days) if on)


def _mask_to_days(mask: int) -> list[bool]:
    return [bool(mask & (1 << i)) for i in range(7)]


class AutomationStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- rules ---------------------------------------------------------------

    def _rule(self, row: sqlite3.Row) -> Rule:
        return Rule(
            id=row["id"],
            name=row["name"],
            enabled=bool(row["enabled"]),
            days=_mask_to_days(row["days"]),
            trigger=json.loads(row["trigger"]),
            targets=json.loads(row["targets"]),
            action=json.loads(row["action"]),
            skip_planned_at=_parse(row["skip_planned_at"]),
            created_at=_parse(row["created_at"]),
            updated_at=_parse(row["updated_at"]),
        )

    def rules(self) -> list[Rule]:
        """In creation order — the tie-break of FR-011."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM automation_rule ORDER BY created_at, id"
            ).fetchall()
        return [self._rule(r) for r in rows]

    def rule(self, rule_id: str) -> Rule | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM automation_rule WHERE id = ?", (rule_id,)
            ).fetchone()
        return self._rule(row) if row else None

    def create(self, draft: RuleDraft, now: datetime | None = None) -> Rule:
        now = now or utcnow()
        rule_id = "r_" + secrets.token_urlsafe(6)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO automation_rule
                    (id, name, enabled, days, trigger, targets, action, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule_id,
                    draft.name,
                    int(draft.enabled),
                    _days_to_mask(draft.days),
                    draft.trigger.model_dump_json(),
                    json.dumps(draft.targets),
                    draft.action.model_dump_json(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        rule = self.rule(rule_id)
        assert rule is not None
        return rule

    def replace(self, rule_id: str, draft: RuleDraft, now: datetime | None = None) -> Rule | None:
        now = now or utcnow()
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE automation_rule
                   SET name = ?, enabled = ?, days = ?, trigger = ?, targets = ?, action = ?,
                       updated_at = ?
                 WHERE id = ?
                """,
                (
                    draft.name,
                    int(draft.enabled),
                    _days_to_mask(draft.days),
                    draft.trigger.model_dump_json(),
                    json.dumps(draft.targets),
                    draft.action.model_dump_json(),
                    now.isoformat(),
                    rule_id,
                ),
            )
        return self.rule(rule_id) if cursor.rowcount else None

    def set_enabled(self, rule_id: str, enabled: bool) -> Rule | None:
        return self._set(rule_id, "enabled", int(enabled))

    def set_skip(self, rule_id: str, planned_at: datetime | None) -> Rule | None:
        return self._set(rule_id, "skip_planned_at", _utc(planned_at) if planned_at else None)

    def _set(self, rule_id: str, column: str, value: Any) -> Rule | None:
        assert column in {"enabled", "skip_planned_at"}
        with self._lock:
            cursor = self._conn.execute(
                f"UPDATE automation_rule SET {column} = ?, updated_at = ? WHERE id = ?",
                (value, utcnow().isoformat(), rule_id),
            )
        return self.rule(rule_id) if cursor.rowcount else None

    def delete(self, rule_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM automation_rule WHERE id = ?", (rule_id,))
        return bool(cursor.rowcount)

    # --- firings -------------------------------------------------------------

    def record_firing(self, firing: Firing) -> bool:
        """Insert a firing. False when this planned instant was already dealt with."""
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO automation_firing
                    (rule_id, planned_at, fired_at, status, outcomes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    firing.rule_id,
                    _utc(firing.planned_at),
                    _utc(firing.fired_at) if firing.fired_at else None,
                    firing.status.value,
                    json.dumps([o.model_dump() for o in firing.outcomes]),
                ),
            )
        return cursor.rowcount == 1

    def finish_firing(self, firing: Firing) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE automation_firing SET fired_at = ?, status = ?, outcomes = ?
                 WHERE rule_id = ? AND planned_at = ?
                """,
                (
                    _utc(firing.fired_at) if firing.fired_at else None,
                    firing.status.value,
                    json.dumps([o.model_dump() for o in firing.outcomes]),
                    firing.rule_id,
                    _utc(firing.planned_at),
                ),
            )

    def has_firing(self, rule_id: str, planned_at: datetime) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM automation_firing WHERE rule_id = ? AND planned_at = ?",
                (rule_id, _utc(planned_at)),
            ).fetchone()
        return row is not None

    def _firing(self, row: sqlite3.Row) -> Firing:
        return Firing(
            rule_id=row["rule_id"],
            planned_at=_parse(row["planned_at"]),
            fired_at=_parse(row["fired_at"]),
            status=FiringStatus(row["status"]),
            outcomes=[Outcome(**o) for o in json.loads(row["outcomes"])],
        )

    def firings(self, rule_id: str, limit: int = 50) -> list[Firing]:
        """Newest first."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM automation_firing WHERE rule_id = ?
                 ORDER BY planned_at DESC LIMIT ?
                """,
                (rule_id, limit),
            ).fetchall()
        return [self._firing(r) for r in rows]

    def last_firing(self, rule_id: str) -> Firing | None:
        found = self.firings(rule_id, limit=1)
        return found[0] if found else None

    def purge_before(self, cutoff: datetime) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM automation_firing WHERE planned_at < ?", (_utc(cutoff),)
            )
        return cursor.rowcount

    # --- settings ------------------------------------------------------------

    def setting(self, key: str) -> Any:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM app_setting WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row["value"]) if row else None

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock:
            if value is None:
                self._conn.execute("DELETE FROM app_setting WHERE key = ?", (key,))
            else:
                self._conn.execute(
                    "INSERT INTO app_setting (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value)),
                )
