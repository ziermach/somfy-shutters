"""Where measurements and derived values are kept.

Runs go to SQLite: they are history, and nobody hand-edits a list of them.
Derived values go to `config/calibration.toml`, because the constitution wants
measured physical values in configuration a person can read, and because a
plain file survives without the app.

`shutters.toml` is never written here. A value a human typed stays exactly as
they typed it — see research.md §2 for the precedence that follows from that.
"""

from __future__ import annotations

import sqlite3
import threading
import tomllib
from datetime import datetime
from pathlib import Path

from .calibration import curve_from_answers, derive
from .config import Settings
from .models import (
    Calibration,
    CheckAnswer,
    CheckReply,
    Direction,
    MeasurementRun,
    RunKind,
    utcnow,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS measurement_run (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    shutter_id    TEXT NOT NULL,
    direction     TEXT NOT NULL,
    dead_seconds  REAL NOT NULL,
    total_seconds REAL NOT NULL,
    recorded_at   TEXT NOT NULL,
    kind          TEXT NOT NULL,
    rejected      TEXT
);
CREATE INDEX IF NOT EXISTS measurement_run_shutter
    ON measurement_run (shutter_id, direction, id);

CREATE TABLE IF NOT EXISTS check_answer (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    shutter_id  TEXT NOT NULL,
    direction   TEXT NOT NULL,
    answer      TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS confirmation_prompt (
    shutter_id TEXT PRIMARY KEY,
    asked_at   TEXT NOT NULL
);
"""

HEADER = """# Written by somfy-shutters. These are measured values.
# To override one, put travel_up_seconds / travel_down_seconds in shutters.toml —
# a value you type there wins, and this file is never consulted for it.
"""


class CalibrationStore:
    def __init__(self, db_path: str | Path, toml_path: str | Path) -> None:
        self.toml_path = Path(toml_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- runs ----------------------------------------------------------------

    def add_run(self, run: MeasurementRun) -> MeasurementRun:
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO measurement_run
                    (shutter_id, direction, dead_seconds, total_seconds,
                     recorded_at, kind, rejected)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.shutter_id,
                    run.direction.value,
                    run.dead_seconds,
                    run.total_seconds,
                    run.recorded_at.isoformat(),
                    run.kind.value,
                    run.rejected,
                ),
            )
        return run.model_copy(update={"id": cursor.lastrowid})

    def runs_for(self, shutter_id: str, direction: Direction | None = None) -> list[MeasurementRun]:
        sql = "SELECT * FROM measurement_run WHERE shutter_id = ?"
        params: list[object] = [shutter_id]
        if direction is not None:
            sql += " AND direction = ?"
            params.append(direction.value)
        sql += " ORDER BY id"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [
            MeasurementRun(
                id=row["id"],
                shutter_id=row["shutter_id"],
                direction=Direction(row["direction"]),
                dead_seconds=row["dead_seconds"],
                total_seconds=row["total_seconds"],
                recorded_at=datetime.fromisoformat(row["recorded_at"]),
                kind=RunKind(row["kind"]),
                rejected=row["rejected"],
            )
            for row in rows
        ]

    def clear_runs(self, shutter_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM measurement_run WHERE shutter_id = ?", (shutter_id,))

    # --- check answers -------------------------------------------------------

    def add_answer(self, answer: CheckAnswer) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO check_answer (shutter_id, direction, answer, recorded_at)"
                " VALUES (?, ?, ?, ?)",
                (
                    answer.shutter_id,
                    answer.direction.value,
                    answer.answer.value,
                    answer.recorded_at.isoformat(),
                ),
            )

    def answers_for(self, shutter_id: str, direction: Direction) -> list[CheckAnswer]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM check_answer WHERE shutter_id = ? AND direction = ? ORDER BY id",
                (shutter_id, direction.value),
            ).fetchall()
        return [
            CheckAnswer(
                shutter_id=row["shutter_id"],
                direction=Direction(row["direction"]),
                answer=CheckReply(row["answer"]),
                recorded_at=datetime.fromisoformat(row["recorded_at"]),
            )
            for row in rows
        ]

    def clear_answers(self, shutter_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM check_answer WHERE shutter_id = ?", (shutter_id,))

    # --- confirmation cooldown ----------------------------------------------

    def last_prompt(self, shutter_id: str) -> datetime | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT asked_at FROM confirmation_prompt WHERE shutter_id = ?", (shutter_id,)
            ).fetchone()
        return datetime.fromisoformat(row["asked_at"]) if row else None

    def note_prompt(self, shutter_id: str, when: datetime) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO confirmation_prompt (shutter_id, asked_at) VALUES (?, ?)
                ON CONFLICT(shutter_id) DO UPDATE SET asked_at = excluded.asked_at
                """,
                (shutter_id, when.isoformat()),
            )

    # --- calibration.toml ----------------------------------------------------

    def read_toml(self) -> dict[str, dict[str, dict[str, object]]]:
        if not self.toml_path.is_file():
            return {}
        try:
            return tomllib.loads(self.toml_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            # A corrupt machine-written file must not stop the house working;
            # the measurements are still in SQLite and can be rewritten.
            return {}

    def write_toml(self, values: dict[str, dict[str, dict[str, object]]]) -> None:
        """Rewritten whole. No comments to preserve — this is the machine's file."""
        lines = [HEADER]
        for shutter_id in sorted(values):
            for direction in ("up", "down"):
                entry = values[shutter_id].get(direction)
                if not entry:
                    continue
                lines.append(f"[{shutter_id}.{direction}]")
                for key in ("travel_seconds", "dead_seconds", "runs", "curve_k"):
                    if key in entry:
                        lines.append(f"{key} = {entry[key]}")
                if entry.get("updated_at"):
                    lines.append(f'updated_at = "{entry["updated_at"]}"')
                lines.append("")
        self.toml_path.parent.mkdir(parents=True, exist_ok=True)
        # Written via a temporary file so a crash mid-write cannot leave a
        # half-file where the travel times should be.
        temp = self.toml_path.with_suffix(".toml.tmp")
        temp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        temp.replace(self.toml_path)


class CalibrationService:
    """Ties the runs, the arithmetic and the configuration layers together.

    The precedence is the whole point and is stated in one place:

        manual in shutters.toml  >  measured in calibration.toml  >  default
    """

    def __init__(self, settings: Settings, store: CalibrationStore) -> None:
        self._settings = settings
        self._store = store
        self._cache: dict[tuple[str, str], Calibration] = {}
        self._load_measured()

    def _load_measured(self) -> None:
        raw = self._store.read_toml()
        for shutter_id, directions in raw.items():
            for name, entry in directions.items():
                if not isinstance(entry, dict) or "travel_seconds" not in entry:
                    continue
                updated = entry.get("updated_at")
                self._cache[(shutter_id, name)] = Calibration(
                    travel_seconds=float(entry["travel_seconds"]),
                    dead_seconds=float(entry.get("dead_seconds", 0.0)),
                    runs=int(entry.get("runs", 0)),
                    curve_k=float(entry.get("curve_k", 0.0)),
                    updated_at=datetime.fromisoformat(str(updated)) if updated else None,
                    source="measured",
                )

    # --- what the rest of the system asks for --------------------------------

    def effective(self, shutter_id: str, direction: Direction | str) -> Calibration:
        name = direction.value if isinstance(direction, Direction) else direction
        manual = self._settings.manual_travel_seconds(shutter_id, name)
        measured = self._cache.get((shutter_id, name))

        if manual is not None:
            # A hand-written value wins, but the measurement is not thrown away:
            # its curve still applies, and the interface can say it is overridden.
            return Calibration(
                travel_seconds=manual,
                dead_seconds=measured.dead_seconds if measured else 0.0,
                runs=measured.runs if measured else 0,
                curve_k=measured.curve_k if measured else 0.0,
                updated_at=measured.updated_at if measured else None,
                source="manual",
            )
        if measured is not None:
            return measured
        return Calibration(
            travel_seconds=self._settings.general.default_travel_seconds, source="default"
        )

    def travel_seconds(self, shutter_id: str, direction: Direction | str) -> float:
        return self.effective(shutter_id, direction).travel_seconds

    def curve_k(self, shutter_id: str, direction: Direction | str) -> float:
        return self.effective(shutter_id, direction).curve_k

    # --- recording -----------------------------------------------------------

    def established_total(self, shutter_id: str, direction: Direction) -> float | None:
        """What a new run is judged against — None while nothing is measured yet."""
        measured = self._cache.get((shutter_id, direction.value))
        return measured.travel_seconds if measured else None

    def record(self, run: MeasurementRun, now: datetime | None = None) -> Calibration | None:
        """Store a run and re-derive. Returns the new value, or None if unchanged."""
        self._store.add_run(run)
        if run.rejected is not None:
            return None
        return self._rederive(run.shutter_id, run.direction, now)

    def _rederive(
        self, shutter_id: str, direction: Direction, now: datetime | None = None
    ) -> Calibration | None:
        runs = self._store.runs_for(shutter_id, direction)
        derived = derive(runs, now=now)
        if derived is None:
            self._cache.pop((shutter_id, direction.value), None)
            self._flush()
            return None
        value = Calibration(
            travel_seconds=round(derived.travel_seconds, 2),
            dead_seconds=round(derived.dead_seconds, 2),
            runs=derived.runs,
            curve_k=curve_from_answers(self._store.answers_for(shutter_id, direction)),
            updated_at=derived.updated_at,
            source="measured",
        )
        self._cache[(shutter_id, direction.value)] = value
        self._flush()
        return value

    def answer_check(
        self, shutter_id: str, direction: Direction, reply: CheckReply, now: datetime | None = None
    ) -> Calibration:
        self._store.add_answer(
            CheckAnswer(
                shutter_id=shutter_id,
                direction=direction,
                answer=reply,
                recorded_at=now or utcnow(),
            )
        )
        current = self._cache.get((shutter_id, direction.value))
        k = curve_from_answers(self._store.answers_for(shutter_id, direction))
        if current is not None:
            self._cache[(shutter_id, direction.value)] = current.model_copy(update={"curve_k": k})
            self._flush()
        return self.effective(shutter_id, direction)

    def clear_checks(self, shutter_id: str) -> None:
        """FR-026: undo verification, leave the measurements alone."""
        self._store.clear_answers(shutter_id)
        for name in ("up", "down"):
            current = self._cache.get((shutter_id, name))
            if current is not None:
                self._cache[(shutter_id, name)] = current.model_copy(update={"curve_k": 0.0})
        self._flush()

    def clear(self, shutter_id: str) -> None:
        """FR-016: discard everything measured. shutters.toml is untouched."""
        self._store.clear_runs(shutter_id)
        self._store.clear_answers(shutter_id)
        for name in ("up", "down"):
            self._cache.pop((shutter_id, name), None)
        self._flush()

    def runs_for(self, shutter_id: str) -> list[MeasurementRun]:
        return self._store.runs_for(shutter_id)

    def _flush(self) -> None:
        values: dict[str, dict[str, dict[str, object]]] = {}
        for (shutter_id, name), value in self._cache.items():
            entry: dict[str, object] = {
                "travel_seconds": value.travel_seconds,
                "dead_seconds": value.dead_seconds,
                "runs": value.runs,
                "curve_k": round(value.curve_k, 3),
            }
            if value.updated_at:
                entry["updated_at"] = value.updated_at.isoformat()
            values.setdefault(shutter_id, {})[name] = entry
        self._store.write_toml(values)
