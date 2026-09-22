"""Feature 005: the household_shutter table (data-model.md)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from somfy_shutters.roster_store import RosterStore


@pytest.fixture
def rows(tmp_path) -> Iterator[RosterStore]:
    store = RosterStore(tmp_path / "state.db")
    yield store
    store.close()


def test_round_trip(rows: RosterStore) -> None:
    rows.insert("bad", "0X279630", "  Bad  ")
    row = rows.get("bad")
    assert row is not None
    assert (row.id, row.address, row.name, row.state) == ("bad", "0x279630", "Bad", "active")
    assert datetime.fromisoformat(row.created_at).tzinfo == UTC
    assert datetime.fromisoformat(row.updated_at).tzinfo == UTC
    assert rows.by_address("0x279630") == row
    assert rows.all() == [row]


def test_survives_reopening(tmp_path) -> None:
    first = RosterStore(tmp_path / "state.db")
    first.insert("bad", "0x279630", "Bad")
    first.close()
    second = RosterStore(tmp_path / "state.db")
    assert [r.id for r in second.all()] == ["bad"]
    second.close()


@pytest.mark.parametrize("bad_id", ["Bad", "bad zimmer", "bäd", ""])
def test_id_shape(rows: RosterStore, bad_id: str) -> None:
    with pytest.raises(ValueError):
        rows.insert(bad_id, "0x279630", "Bad")


@pytest.mark.parametrize("name", ["", "   ", "x" * 41])
def test_name_length(rows: RosterStore, name: str) -> None:
    with pytest.raises(ValueError):
        rows.insert("bad", "0x279630", name)


def test_forty_characters_are_fine(rows: RosterStore) -> None:
    rows.insert("bad", "0x279630", "x" * 40)
    assert rows.get("bad").name == "x" * 40  # type: ignore[union-attr]


def test_address_unique(rows: RosterStore) -> None:
    rows.insert("bad", "0x279630", "Bad")
    with pytest.raises(sqlite3.IntegrityError):
        rows.insert("bad-2", "0X279630", "Bad oben")


def test_name_unique_among_active(rows: RosterStore) -> None:
    rows.insert("bad", "0x279630", "Bad")
    with pytest.raises(ValueError):
        rows.insert("bad-2", "0x279631", "bad")


def test_rename_keeps_id(rows: RosterStore) -> None:
    rows.insert("bad", "0x279630", "Bad")
    rows.rename("bad", "Badezimmer")
    row = rows.get("bad")
    assert (row.id, row.name) == ("bad", "Badezimmer")  # type: ignore[union-attr]


def test_state_only_active_or_set_aside(rows: RosterStore) -> None:
    rows.insert("bad", "0x279630", "Bad")
    rows.set_state("bad", "set_aside")
    assert rows.get("bad").state == "set_aside"  # type: ignore[union-attr]
    with pytest.raises(ValueError):
        rows.set_state("bad", "forgotten")


def test_delete(rows: RosterStore) -> None:
    rows.insert("bad", "0x279630", "Bad")
    assert rows.delete("bad")
    assert rows.get("bad") is None
    assert not rows.delete("bad")
