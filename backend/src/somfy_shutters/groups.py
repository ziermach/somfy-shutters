"""Groups of shutters (specs/004-shutter-groups/data-model.md).

A group is the household's name for a set of shutters, nothing more: it owns no
state, and deleting it changes no shutter. Membership is many-to-many, so a
shutter can be in "Wohnzimmer", "Erdgeschoss" and "Südseite" at once.
"""

from __future__ import annotations

import secrets
import sqlite3
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import utcnow

MAX_NAME = 40

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS shutter_group (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    name_key    TEXT NOT NULL UNIQUE,
    position    INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shutter_group_member (
    group_id    TEXT NOT NULL REFERENCES shutter_group(id) ON DELETE CASCADE,
    shutter_id  TEXT NOT NULL,
    position    INTEGER NOT NULL,
    PRIMARY KEY (group_id, shutter_id)
);
"""


def name_key(name: str) -> str:
    """What two names have to share to be the same name (FR-003)."""
    return unicodedata.normalize("NFC", name.strip()).casefold()


class GroupDraft(BaseModel):
    """What a person edits."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    members: list[str] = Field(min_length=1)
    """In display order. Whether each is configured is the caller's to check: the
    model does not know the configuration."""

    @field_validator("name")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        value = unicodedata.normalize("NFC", value.strip())
        if not value:
            raise ValueError("name must not be blank")
        if len(value) > MAX_NAME:
            raise ValueError(f"name must be at most {MAX_NAME} characters")
        return value

    @field_validator("members")
    @classmethod
    def _a_set(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("a shutter is listed twice")
        return value


class Group(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    members: list[str]
    """May be empty: only when every member left the configuration (FR-009)."""

    def wire(self) -> dict[str, object]:
        return {"id": self.id, "name": self.name, "members": list(self.members)}


class NameTaken(ValueError):
    def __init__(self, group_id: str) -> None:
        super().__init__(group_id)
        self.group_id = group_id


class NotAPermutation(ValueError):
    """A reorder that does not name every group exactly once."""


class GroupStore:
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

    # --- reading -------------------------------------------------------------

    def _members(self) -> dict[str, list[str]]:
        rows = self._conn.execute(
            "SELECT group_id, shutter_id FROM shutter_group_member ORDER BY group_id, position"
        ).fetchall()
        out: dict[str, list[str]] = {}
        for row in rows:
            out.setdefault(row["group_id"], []).append(row["shutter_id"])
        return out

    def groups(self) -> list[Group]:
        """In the household's order."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name FROM shutter_group ORDER BY position, created_at"
            ).fetchall()
            members = self._members()
        return [Group(id=r["id"], name=r["name"], members=members.get(r["id"], [])) for r in rows]

    def get(self, group_id: str) -> Group | None:
        return next((g for g in self.groups() if g.id == group_id), None)

    # --- writing -------------------------------------------------------------

    def _holder_of(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT id FROM shutter_group WHERE name_key = ?", (key,)
        ).fetchone()
        return row["id"] if row else None

    def _write_members(self, group_id: str, members: list[str]) -> None:
        self._conn.execute("DELETE FROM shutter_group_member WHERE group_id = ?", (group_id,))
        self._conn.executemany(
            "INSERT INTO shutter_group_member (group_id, shutter_id, position) VALUES (?, ?, ?)",
            [(group_id, sid, i) for i, sid in enumerate(members)],
        )

    def create(self, draft: GroupDraft, now: datetime | None = None) -> Group:
        """Appended last. Raises NameTaken."""
        now = now or utcnow()
        group_id = "g_" + secrets.token_urlsafe(6)
        key = name_key(draft.name)
        with self._lock:
            holder = self._holder_of(key)
            if holder is not None:
                raise NameTaken(holder)
            self._conn.execute("BEGIN")
            try:
                (last,) = self._conn.execute(
                    "SELECT COALESCE(MAX(position), -1) FROM shutter_group"
                ).fetchone()
                self._conn.execute(
                    """
                    INSERT INTO shutter_group (id, name, name_key, position, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (group_id, draft.name, key, last + 1, now.isoformat(), now.isoformat()),
                )
                self._write_members(group_id, draft.members)
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
        return Group(id=group_id, name=draft.name, members=list(draft.members))

    def update(self, group_id: str, draft: GroupDraft, now: datetime | None = None) -> Group | None:
        """Replaces name and members. None if there is no such group; raises NameTaken."""
        now = now or utcnow()
        key = name_key(draft.name)
        with self._lock:
            holder = self._holder_of(key)
            if holder is not None and holder != group_id:
                raise NameTaken(holder)
            self._conn.execute("BEGIN")
            try:
                cursor = self._conn.execute(
                    "UPDATE shutter_group SET name = ?, name_key = ?, updated_at = ? WHERE id = ?",
                    (draft.name, key, now.isoformat(), group_id),
                )
                if not cursor.rowcount:
                    self._conn.execute("ROLLBACK")
                    return None
                self._write_members(group_id, draft.members)
                self._conn.execute("COMMIT")
            except BaseException:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise
        return Group(id=group_id, name=draft.name, members=list(draft.members))

    def delete(self, group_id: str) -> bool:
        """Memberships go with it (ON DELETE CASCADE); shutters are not touched."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM shutter_group WHERE id = ?", (group_id,))
        return bool(cursor.rowcount)

    def reorder(self, ids: list[str]) -> list[Group]:
        """Raises NotAPermutation unless every existing group is named exactly once."""
        with self._lock:
            existing = [r["id"] for r in self._conn.execute("SELECT id FROM shutter_group")]
            if len(ids) != len(existing) or set(ids) != set(existing):
                raise NotAPermutation(ids)
            self._conn.execute("BEGIN")
            self._conn.executemany(
                "UPDATE shutter_group SET position = ? WHERE id = ?",
                [(i, gid) for i, gid in enumerate(ids)],
            )
            self._conn.execute("COMMIT")
        return self.groups()

    def prune(self, configured: list[str]) -> bool:
        """Drop memberships of shutters no longer configured (research §8).

        Run at startup, the only moment the configuration can change. Without it a
        shutter removed and later re-added under the same id would quietly rejoin
        its old groups. A group left empty is kept; the household decides.
        """
        with self._lock:
            placeholders = ",".join("?" for _ in configured) or "''"
            cursor = self._conn.execute(
                f"DELETE FROM shutter_group_member WHERE shutter_id NOT IN ({placeholders})",
                configured,
            )
        return bool(cursor.rowcount)
