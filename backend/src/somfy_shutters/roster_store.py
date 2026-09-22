"""The household_shutter table: shutters confirmed from the bridge's announcements.

Hand-configured shutters are not stored here — shutters.toml stays their only record,
and the app never writes it (feature 005, data-model.md).
"""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import ID_PATTERN
from .models import utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS household_shutter (
    id          TEXT PRIMARY KEY,
    address     TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    state       TEXT NOT NULL CHECK (state IN ('active', 'set_aside')),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

NAME_MAX = 40
RowState = Literal["active", "set_aside"]


@dataclass(frozen=True)
class HouseholdRow:
    id: str
    address: str
    name: str
    state: RowState
    created_at: str
    updated_at: str


def clean_name(name: str) -> str:
    """1 to 40 characters, trimmed."""
    trimmed = name.strip()
    if not 1 <= len(trimmed) <= NAME_MAX:
        raise ValueError(f"name must be 1 to {NAME_MAX} characters, got {len(trimmed)}")
    return trimmed


class RosterStore:
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

    @staticmethod
    def _row(row: sqlite3.Row) -> HouseholdRow:
        # SELECT * returns the columns in the table's order, which is the dataclass's.
        return HouseholdRow(*row)

    def all(self) -> list[HouseholdRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM household_shutter ORDER BY created_at, id"
            ).fetchall()
        return [self._row(r) for r in rows]

    def get(self, shutter_id: str) -> HouseholdRow | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM household_shutter WHERE id = ?", (shutter_id,)
            ).fetchone()
        return self._row(row) if row else None

    def by_address(self, address: str) -> HouseholdRow | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM household_shutter WHERE address = ?", (address.strip().lower(),)
            ).fetchone()
        return self._row(row) if row else None

    def _name_in_use(self, name: str, except_id: str | None = None) -> bool:
        return any(
            r.name.casefold() == name.casefold() and r.id != except_id and r.state == "active"
            for r in self.all()
        )

    def insert(self, shutter_id: str, address: str, name: str) -> HouseholdRow:
        if not re.match(ID_PATTERN, shutter_id):
            raise ValueError(f"id must match {ID_PATTERN}, got {shutter_id!r}")
        name = clean_name(name)
        if self._name_in_use(name):
            raise ValueError(f"name {name!r} is already used")
        now = utcnow().isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO household_shutter VALUES (?, ?, ?, 'active', ?, ?)",
                (shutter_id, address.strip().lower(), name, now, now),
            )
        row = self.get(shutter_id)
        assert row is not None
        return row

    def rename(self, shutter_id: str, name: str) -> HouseholdRow | None:
        name = clean_name(name)
        if self._name_in_use(name, except_id=shutter_id):
            raise ValueError(f"name {name!r} is already used")
        with self._lock:
            self._conn.execute(
                "UPDATE household_shutter SET name = ?, updated_at = ? WHERE id = ?",
                (name, utcnow().isoformat(), shutter_id),
            )
        return self.get(shutter_id)

    def set_state(self, shutter_id: str, state: str) -> None:
        if state not in ("active", "set_aside"):
            raise ValueError(f"state must be active or set_aside, got {state!r}")
        with self._lock:
            self._conn.execute(
                "UPDATE household_shutter SET state = ?, updated_at = ? WHERE id = ?",
                (state, utcnow().isoformat(), shutter_id),
            )

    def delete(self, shutter_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM household_shutter WHERE id = ?", (shutter_id,))
        return bool(cursor.rowcount)
