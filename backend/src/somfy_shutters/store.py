"""Persistence of shutter state.

Written when a movement starts and when it settles — never per animation frame.
The ``was_moving`` flag is what makes FR-010 exact: a shutter interrupted
mid-travel is indistinguishable from one that settled unless we record that it
was in motion.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .models import Confidence, PositionEstimate, Source

SCHEMA = """
CREATE TABLE IF NOT EXISTS shutter_state (
    shutter_id  TEXT PRIMARY KEY,
    percent     INTEGER,
    confidence  TEXT NOT NULL,
    certain_at  TEXT,
    source      TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    was_moving  INTEGER NOT NULL DEFAULT 0
);
"""

UPSERT = """
INSERT INTO shutter_state
    (shutter_id, percent, confidence, certain_at, source, updated_at, was_moving)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(shutter_id) DO UPDATE SET
    percent = excluded.percent,
    confidence = excluded.confidence,
    certain_at = excluded.certain_at,
    source = excluded.source,
    updated_at = excluded.updated_at,
    was_moving = excluded.was_moving
"""


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # The connection is created wherever the app is built but used from the
        # event loop, and those are not guaranteed to be the same thread. A lock
        # is enough serialisation here: writes happen when a movement starts and
        # when it settles, not per frame.
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def save(
        self,
        shutter_id: str,
        position: PositionEstimate,
        *,
        was_moving: bool,
        now: datetime,
    ) -> None:
        row = (
            shutter_id,
            position.percent,
            position.confidence.value,
            position.certain_at.isoformat() if position.certain_at else None,
            position.source.value,
            now.isoformat(),
            int(was_moving),
        )
        with self._lock:
            self._conn.execute(UPSERT, row)

    def delete(self, shutter_id: str) -> None:
        """A shutter left the household (feature 005)."""
        with self._lock:
            self._conn.execute("DELETE FROM shutter_state WHERE shutter_id = ?", (shutter_id,))

    def load_all(self) -> dict[str, PositionEstimate]:
        """Restore positions. A shutter that was travelling comes back unknown."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM shutter_state").fetchall()

        restored: dict[str, PositionEstimate] = {}
        for row in rows:
            confidence = Confidence(row["confidence"])
            if row["was_moving"] or confidence is Confidence.UNKNOWN:
                restored[row["shutter_id"]] = PositionEstimate.unknown()
                continue
            restored[row["shutter_id"]] = PositionEstimate(
                percent=row["percent"],
                confidence=confidence,
                certain_at=datetime.fromisoformat(row["certain_at"]) if row["certain_at"] else None,
                # It came out of storage, whatever originally produced it.
                source=Source.RESTORED,
            )
        return restored
