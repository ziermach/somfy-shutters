"""T007: credentials and pairing codes in SQLite (feature 007, data-model.md)."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta

import pytest

from somfy_shutters.auth.models import ALL_ABILITIES, Ability
from somfy_shutters.auth.store import AuthStore

WATCH_COMMAND = frozenset({Ability.WATCH, Ability.COMMAND})


class Clocks:
    def __init__(self) -> None:
        self.wall = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
        self.mono = 1000.0

    def now(self) -> datetime:
        return self.wall

    def monotonic(self) -> float:
        return self.mono

    def advance(self, seconds: float) -> None:
        self.wall += timedelta(seconds=seconds)
        self.mono += seconds


@pytest.fixture
def clocks() -> Clocks:
    return Clocks()


@pytest.fixture
def auth(tmp_path, clocks):
    store = AuthStore(tmp_path / "state.db", clock=clocks.now, monotonic=clocks.monotonic)
    yield store
    store.close()


def every_value(db) -> list[str]:
    conn = sqlite3.connect(db)
    values = []
    for table in ("credential", "pairing_code"):
        for row in conn.execute(f"SELECT * FROM {table}"):
            values.extend(str(v) for v in row if v is not None)
    conn.close()
    return values


def test_the_token_is_never_stored(tmp_path, auth) -> None:
    _, token = auth.issue("Küche", WATCH_COMMAND)
    assert all(token not in v for v in every_value(tmp_path / "state.db"))


def test_issued_credential_resolves_with_watch_added(auth) -> None:
    credential, token = auth.issue("Kurzbefehl", frozenset({Ability.COMMAND}))
    assert auth.resolve(token) == credential
    assert credential.abilities == WATCH_COMMAND
    assert credential.origin == "issued"


def test_resolve_says_why_not(auth, clocks) -> None:
    assert auth.resolve("nonsense") == "malformed"
    assert auth.resolve("sst_" + "A" * 52) == "unknown"
    revoked, revoked_token = auth.issue("A", WATCH_COMMAND)
    auth.revoke(revoked.id, by=None)
    assert auth.resolve(revoked_token) == "revoked"
    _, expiring = auth.issue("B", WATCH_COMMAND, expires_at=clocks.wall + timedelta(hours=1))
    clocks.advance(3601)
    assert auth.resolve(expiring) == "expired"


def test_revocation_is_terminal(auth) -> None:
    credential, _ = auth.issue("A", WATCH_COMMAND)
    assert auth.revoke(credential.id, by=None) is True
    assert auth.revoke(credential.id, by=None) is False
    assert auth.get(credential.id).state(datetime.now(UTC)) == "revoked"


def test_last_used_is_written_at_most_once_a_minute(auth, clocks) -> None:
    credential, _ = auth.issue("A", WATCH_COMMAND)
    auth.touch(credential.id)
    first = auth.get(credential.id).last_used_at
    clocks.advance(30)
    auth.touch(credential.id)
    assert auth.get(credential.id).last_used_at == first
    clocks.advance(31)
    auth.touch(credential.id)
    assert auth.get(credential.id).last_used_at > first


def test_a_code_is_exchanged_once_for_exactly_its_abilities(auth) -> None:
    owner, _ = auth.issue("Owner", ALL_ABILITIES)
    record, code = auth.mint(WATCH_COMMAND, owner.id, minutes=5)
    _, credential, token = auth.redeem(code.lower(), "Annas Handy")
    assert credential.abilities == WATCH_COMMAND
    assert credential.origin == "paired" and credential.created_by == owner.id
    assert auth.resolve(token) == credential
    assert auth.code(record.id).credential_id == credential.id
    assert auth.redeem(code, "Zweiter Versuch") == "spent"


def test_the_code_is_never_stored(tmp_path, auth) -> None:
    _, code = auth.mint(WATCH_COMMAND, None, minutes=5)
    assert all(code not in v for v in every_value(tmp_path / "state.db"))


def test_refused_codes(auth, clocks) -> None:
    owner, _ = auth.issue("Owner", ALL_ABILITIES)
    assert auth.redeem("nope", "x") == "malformed"
    assert auth.redeem("000000", "x") == "unknown"

    cancelled, code = auth.mint(WATCH_COMMAND, owner.id, minutes=5)
    auth.cancel(cancelled.id)
    assert auth.redeem(code, "x") == "cancelled"

    _, late = auth.mint(WATCH_COMMAND, owner.id, minutes=5)
    clocks.advance(301)
    assert auth.redeem(late, "x") == "expired"

    _, orphan = auth.mint(WATCH_COMMAND, owner.id, minutes=5)
    auth.revoke(owner.id, by=None)
    assert auth.redeem(orphan, "x") == "minter_revoked"


def test_a_failed_attempt_still_spends_the_code(auth) -> None:
    owner, _ = auth.issue("Owner", ALL_ABILITIES)
    record, code = auth.mint(WATCH_COMMAND, owner.id, minutes=5)
    auth.revoke(owner.id, by=None)
    assert auth.redeem(code, "x") == "minter_revoked"
    assert auth.code(record.id).spent_at is not None


def test_recovery_codes_need_no_minter(auth) -> None:
    _, code = auth.mint(ALL_ABILITIES, None, minutes=15)
    _, credential, _ = auth.redeem(code, "Laptop")
    assert credential.origin == "recovery" and credential.abilities == ALL_ABILITIES


def test_two_processes_racing_for_one_code_make_one_credential(tmp_path) -> None:
    """Two connections to one file, as the service and the console command are."""
    first = AuthStore(tmp_path / "state.db")
    second = AuthStore(tmp_path / "state.db")
    _, code = first.mint(WATCH_COMMAND, None, minutes=5)
    results: list[object] = []
    barrier = threading.Barrier(2)

    def race(store: AuthStore, name: str) -> None:
        barrier.wait()
        results.append(store.redeem(code, name))

    threads = [threading.Thread(target=race, args=(s, n)) for s, n in ((first, "A"), (second, "B"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(type(r).__name__ for r in results) == ["str", "tuple"]
    assert len(first.list()) == 1
    first.close()
    second.close()


def test_cancelling_what_a_credential_minted(auth) -> None:
    owner, _ = auth.issue("Owner", ALL_ABILITIES)
    other, _ = auth.issue("Other", ALL_ABILITIES)
    mine, _ = auth.mint(WATCH_COMMAND, owner.id, minutes=5)
    theirs, _ = auth.mint(WATCH_COMMAND, other.id, minutes=5)
    assert auth.cancel_minted_by(owner.id) == [mine.id]
    assert [c.id for c in auth.outstanding()] == [theirs.id]
    assert auth.cancel_outstanding() == [theirs.id]
    assert auth.outstanding() == []


def test_permanent_managers(auth, clocks) -> None:
    owner, _ = auth.issue("Owner", ALL_ABILITIES)
    auth.issue("Befristet", ALL_ABILITIES, expires_at=clocks.wall + timedelta(days=30))
    auth.issue("Nur fahren", WATCH_COMMAND)
    assert auth.permanent_managers() == 1
    assert auth.permanent_managers(excluding=owner.id) == 0
