"""T009: the record keeps its order, its names, and never gets in the way."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest

from somfy_shutters.auth.audit import AuditLog
from somfy_shutters.auth.models import Actor

ANNA = Actor("credential", "c_anna", "Anna")
KUECHE = Actor("credential", "c_kueche", "Küche")


class Wall:
    def __init__(self) -> None:
        self.at = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.at


@pytest.fixture
def wall() -> Wall:
    return Wall()


@pytest.fixture
def audit(tmp_path, wall):
    log = AuditLog(tmp_path / "state.db", clock=wall)
    yield log
    log.close()


def test_newest_first_by_id_even_when_the_clock_goes_back(audit, wall) -> None:
    audit.record(ANNA, "command", "accepted", shutter_id="wohnzimmer")
    wall.at -= timedelta(hours=6)  # a Pi booting with a stale clock
    audit.record(KUECHE, "command", "accepted", shutter_id="wohnzimmer", clock_ok=False)
    first, second = audit.query()
    assert first.actor.name == "Küche" and first.clock_ok is False
    assert second.actor.name == "Anna"
    assert first.at < second.at  # wall time as recorded; order by id regardless


def test_filters_and_paging(audit) -> None:
    for i in range(5):
        audit.record(ANNA if i % 2 else KUECHE, "command", "accepted", shutter_id=f"s{i % 2}")
    assert {e.shutter_id for e in audit.query(shutter="s1")} == {"s1"}
    assert {e.actor.id for e in audit.query(actor="c_anna")} == {"c_anna"}
    page = audit.query(limit=2)
    rest = audit.query(before=page[-1].id)
    assert [e.id for e in page + rest] == sorted((e.id for e in page + rest), reverse=True)
    assert len(page + rest) == 5


def test_limit_is_capped(audit) -> None:
    for _ in range(250):
        audit.record(ANNA, "command", "accepted")
    assert len(audit.query(limit=10_000)) == 200


def test_detail_round_trips(audit) -> None:
    audit.record(ANNA, "command", "accepted", detail={"action": "position", "percent": 30})
    assert audit.query()[0].detail == {"action": "position", "percent": 30}


def test_purge(audit, wall) -> None:
    audit.record(ANNA, "command", "accepted")
    wall.at += timedelta(days=200)
    audit.record(ANNA, "command", "accepted")
    assert audit.purge(wall.at - timedelta(days=180)) == 1
    assert len(audit.query()) == 1


def test_a_failed_write_logs_and_returns(tmp_path, caplog) -> None:
    log = AuditLog(tmp_path / "state.db")
    log.close()
    with caplog.at_level(logging.ERROR):
        log.record(ANNA, "command", "accepted")  # must not raise
    assert "could not record command" in caplog.text


def test_the_name_is_kept_as_it_was(audit) -> None:
    audit.record(ANNA, "command", "accepted")
    # Nothing here looks the name up later: revoking or renaming Anna cannot change it.
    assert audit.query(actor="c_anna")[0].actor.name == "Anna"
