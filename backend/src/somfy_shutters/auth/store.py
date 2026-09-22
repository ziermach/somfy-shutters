"""Credentials and pairing codes, in the app's SQLite database.

A credential's value is never stored — only its SHA-256 (FR-004). It exists in full
once, in the response that issued it. Pairing codes are stored the same way.

The console command (`somfy-shutters auth recover`) opens this same file from a
second process, so writes that must not interleave use `BEGIN IMMEDIATE`, and the
connection waits for a lock instead of failing.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from ..models import utcnow
from . import tokens
from .models import Ability, Credential, PairingCode, with_watch

SCHEMA = """
CREATE TABLE IF NOT EXISTS credential (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    secret_hash   TEXT NOT NULL UNIQUE,
    abilities     TEXT NOT NULL,
    origin        TEXT NOT NULL,
    created_by    TEXT,
    created_at    TEXT NOT NULL,
    last_used_at  TEXT,
    expires_at    TEXT,
    revoked_at    TEXT,
    revoked_by    TEXT
);

CREATE TABLE IF NOT EXISTS pairing_code (
    id            TEXT PRIMARY KEY,
    code_hash     TEXT NOT NULL UNIQUE,
    abilities     TEXT NOT NULL,
    minted_by     TEXT,
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    spent_at      TEXT,
    cancelled_at  TEXT,
    credential_id TEXT
);
"""

TOUCH_EVERY = 60.0
"""Seconds between writes of last_used_at for one credential (research §12)."""


def _iso(at: datetime | None) -> str | None:
    return at.isoformat() if at else None


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _abilities(raw: str) -> frozenset[Ability]:
    return frozenset(Ability(a) for a in json.loads(raw))


def _dump(abilities: frozenset[Ability]) -> str:
    return json.dumps(sorted(a.value for a in abilities))


class AuthStore:
    def __init__(
        self,
        db_path: str | Path,
        clock: Callable[[], datetime] = utcnow,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.monotonic = monotonic
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            db_path, isolation_level=None, check_same_thread=False, timeout=10
        )
        self._conn.row_factory = sqlite3.Row
        self._touched: dict[str, float] = {}
        with self._lock:
            # WAL: the record is read while commands are written (research §9).
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- credentials ---------------------------------------------------------

    @staticmethod
    def _credential(row: sqlite3.Row) -> Credential:
        return Credential(
            id=row["id"],
            name=row["name"],
            abilities=_abilities(row["abilities"]),
            origin=row["origin"],
            created_by=row["created_by"],
            created_at=_parse(row["created_at"]),  # type: ignore[arg-type]
            last_used_at=_parse(row["last_used_at"]),
            expires_at=_parse(row["expires_at"]),
            revoked_at=_parse(row["revoked_at"]),
        )

    def _insert_credential(
        self,
        name: str,
        abilities: frozenset[Ability],
        origin: str,
        created_by: str | None,
        expires_at: datetime | None,
    ) -> tuple[str, str]:
        """Inside the caller's lock (and transaction, if any)."""
        credential_id = "c_" + secrets.token_urlsafe(6)
        token = tokens.new_token()
        self._conn.execute(
            """
            INSERT INTO credential
                (id, name, secret_hash, abilities, origin, created_by, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                credential_id,
                name,
                tokens.digest(token),
                _dump(with_watch(abilities)),
                origin,
                created_by,
                self.clock().isoformat(),
                _iso(expires_at),
            ),
        )
        return credential_id, token

    def issue(
        self,
        name: str,
        abilities: frozenset[Ability],
        origin: str = "issued",
        created_by: str | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[Credential, str]:
        """The credential and its token. The token is not kept anywhere (FR-006)."""
        with self._lock:
            credential_id, token = self._insert_credential(
                name, abilities, origin, created_by, expires_at
            )
        credential = self.get(credential_id)
        assert credential is not None
        return credential, token

    def get(self, credential_id: str) -> Credential | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM credential WHERE id = ?", (credential_id,)
            ).fetchone()
        return self._credential(row) if row else None

    def list(self) -> list[Credential]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM credential ORDER BY created_at, id").fetchall()
        return [self._credential(r) for r in rows]

    def resolve(self, token: str) -> Credential | str:
        """The active credential, or why not: malformed, unknown, expired, revoked."""
        if not tokens.looks_like_token(token):
            return "malformed"
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM credential WHERE secret_hash = ?", (tokens.digest(token),)
            ).fetchone()
        if row is None:
            return "unknown"
        credential = self._credential(row)
        state = credential.state(self.clock())
        return credential if state == "active" else state

    def revoke(self, credential_id: str, by: str | None) -> bool:
        """True if this call revoked it; revocation is terminal."""
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE credential SET revoked_at = ?, revoked_by = ? "
                "WHERE id = ? AND revoked_at IS NULL",
                (self.clock().isoformat(), by, credential_id),
            )
        return bool(cursor.rowcount)

    def touch(self, credential_id: str) -> None:
        """Note use, but write at most once a minute per credential."""
        now = self.monotonic()
        last = self._touched.get(credential_id)
        if last is not None and now - last < TOUCH_EVERY:
            return
        self._touched[credential_id] = now
        with self._lock:
            self._conn.execute(
                "UPDATE credential SET last_used_at = ? WHERE id = ?",
                (self.clock().isoformat(), credential_id),
            )

    def permanent_managers(self, excluding: str | None = None) -> int:
        """Active credentials that may manage and never expire (research §13)."""
        now = self.clock()
        return sum(
            1
            for c in self.list()
            if c.id != excluding
            and Ability.MANAGE in c.abilities
            and c.expires_at is None
            and c.state(now) == "active"
        )

    def expired_between(self, start: datetime, end: datetime) -> list[Credential]:
        return [
            c
            for c in self.list()
            if c.revoked_at is None and c.expires_at is not None and start < c.expires_at <= end
        ]

    # --- pairing codes ---------------------------------------------------------

    @staticmethod
    def _code(row: sqlite3.Row) -> PairingCode:
        return PairingCode(
            id=row["id"],
            abilities=_abilities(row["abilities"]),
            minted_by=row["minted_by"],
            created_at=_parse(row["created_at"]),  # type: ignore[arg-type]
            expires_at=_parse(row["expires_at"]),  # type: ignore[arg-type]
            spent_at=_parse(row["spent_at"]),
            cancelled_at=_parse(row["cancelled_at"]),
            credential_id=row["credential_id"],
        )

    def mint(
        self, abilities: frozenset[Ability], minted_by: str | None, minutes: float
    ) -> tuple[PairingCode, str]:
        """The code record and the six characters, which are not kept anywhere."""
        now = self.clock()
        code_id = "p_" + secrets.token_urlsafe(6)
        with self._lock:
            while True:  # 10^9 codes; a clash with a stored one is possible, not likely
                code = tokens.new_code()
                try:
                    self._conn.execute(
                        """
                        INSERT INTO pairing_code
                            (id, code_hash, abilities, minted_by, created_at, expires_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            code_id,
                            tokens.digest(code),
                            _dump(with_watch(abilities)),
                            minted_by,
                            now.isoformat(),
                            (now + timedelta(minutes=minutes)).isoformat(),
                        ),
                    )
                    break
                except sqlite3.IntegrityError:
                    continue
        record = self.code(code_id)
        assert record is not None
        return record, code

    def code(self, code_id: str) -> PairingCode | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM pairing_code WHERE id = ?", (code_id,)
            ).fetchone()
        return self._code(row) if row else None

    def outstanding(self) -> list[PairingCode]:
        now = self.clock()
        with self._lock:
            rows = self._conn.execute("SELECT * FROM pairing_code ORDER BY created_at").fetchall()
        return [c for c in (self._code(r) for r in rows) if c.outstanding(now)]

    def codes_expired_between(self, start: datetime, end: datetime) -> list[PairingCode]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM pairing_code WHERE spent_at IS NULL AND cancelled_at IS NULL"
            ).fetchall()
        return [c for c in (self._code(r) for r in rows) if start < c.expires_at <= end]

    def redeem(self, typed: str, name: str) -> tuple[PairingCode, Credential, str] | str:
        """Exchange a code for a new credential and its token, once (FR-031).

        One transaction: two devices racing for the same code are serialised by
        SQLite's write lock, and the second finds it spent. The code is spent by
        the attempt, whether or not the exchange then succeeds.
        """
        code = tokens.normalise_code(typed)
        if code is None:
            return "malformed"
        now = self.clock()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT * FROM pairing_code WHERE code_hash = ?", (tokens.digest(code),)
                ).fetchone()
                if row is None:
                    self._conn.execute("ROLLBACK")
                    return "unknown"
                record = self._code(row)
                if record.spent_at is None:
                    self._conn.execute(
                        "UPDATE pairing_code SET spent_at = ? WHERE id = ?",
                        (now.isoformat(), record.id),
                    )
                reason = self._unredeemable(record, now)
                if reason is not None:
                    self._conn.execute("COMMIT")
                    return reason
                origin = "recovery" if record.minted_by is None else "paired"
                credential_id, token = self._insert_credential(
                    name, record.abilities, origin, record.minted_by, None
                )
                self._conn.execute(
                    "UPDATE pairing_code SET credential_id = ? WHERE id = ?",
                    (credential_id, record.id),
                )
                self._conn.execute("COMMIT")
            except BaseException:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise
        credential = self.get(credential_id)
        assert credential is not None
        return record, credential, token

    def _unredeemable(self, record: PairingCode, now: datetime) -> str | None:
        if record.spent_at is not None:
            return "spent"
        if record.cancelled_at is not None:
            return "cancelled"
        if record.expires_at <= now:
            return "expired"
        if record.minted_by is not None:
            row = self._conn.execute(
                "SELECT * FROM credential WHERE id = ?", (record.minted_by,)
            ).fetchone()
            if row is None or self._credential(row).state(now) != "active":
                # The code must not outlive the authority that created it.
                return "minter_revoked"
        return None

    def cancel(self, code_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE pairing_code SET cancelled_at = ? "
                "WHERE id = ? AND spent_at IS NULL AND cancelled_at IS NULL",
                (self.clock().isoformat(), code_id),
            )
        return bool(cursor.rowcount)

    def cancel_minted_by(self, credential_id: str) -> list[str]:
        ids = [c.id for c in self.outstanding() if c.minted_by == credential_id]
        return [i for i in ids if self.cancel(i)]

    def cancel_outstanding(self) -> list[str]:
        return [c.id for c in self.outstanding() if self.cancel(c.id)]
