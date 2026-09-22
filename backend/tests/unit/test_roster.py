"""Feature 005: the roster — what the bridge announces vs. what the household confirmed.

No broker and no app: announcements are fed in as the adapter would hand them up.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from somfy_shutters.bridge.base import Report
from somfy_shutters.config import Settings
from somfy_shutters.roster import NameTaken, NotAnnounced, Roster, slug
from somfy_shutters.roster_store import RosterStore

from ..conftest import CONFIG


def announce(address: str, name: str | None, *, retained: bool = True) -> Report:
    return Report(address, kind="announcement", name=name, retained=retained)


@pytest.fixture
def rows(tmp_path) -> Iterator[RosterStore]:
    store = RosterStore(tmp_path / "state.db")
    yield store
    store.close()


@pytest.fixture
def settings() -> Settings:
    return Settings.model_validate(CONFIG)


@pytest.fixture
def roster(settings: Settings, rows: RosterStore) -> Roster:
    return Roster(settings, rows)


async def test_announced_and_unknown_is_new(roster: Roster) -> None:
    await roster.handle(announce("0x279630", "Bad"))
    await roster.handle(announce("0x279631", "Gästezimmer"))
    assert [(a.address, a.name) for a in roster.new()] == [
        ("0x279630", "Bad"),
        ("0x279631", "Gästezimmer"),
    ]


async def test_new_is_not_in_the_household(roster: Roster, settings: Settings) -> None:
    await roster.handle(announce("0x279630", "Bad"))
    assert settings.by_address("0x279630") is None
    assert "bad" not in settings.shutters


async def test_a_configured_address_is_never_new(roster: Roster) -> None:
    await roster.handle(announce("0x279621", "Living Room"))
    assert roster.new() == []
    [entry] = [e for e in roster.active() if e.id == "wohnzimmer"]
    assert (entry.name, entry.origin) == ("Wohnzimmer", "config")


async def test_withdrawn_is_not_new(roster: Roster) -> None:
    await roster.handle(announce("0x279630", "Bad"))
    await roster.handle(announce("0x279630", None))
    assert roster.new() == []


async def test_confirm_appends_to_the_household(roster: Roster, settings: Settings) -> None:
    await roster.handle(announce("0x279630", "Bad"))
    shutter = await roster.confirm("0x279630", "  Bad  ")
    assert (shutter.id, shutter.name, shutter.address) == ("bad", "Bad", "0x279630")
    assert settings.by_address("0x279630") is shutter
    assert settings.shutters["bad"].travel_up_seconds is None
    assert roster.new() == []
    [entry] = [e for e in roster.active() if e.id == "bad"]
    assert entry.origin == "bridge"


async def test_confirm_needs_a_current_announcement(roster: Roster) -> None:
    with pytest.raises(NotAnnounced):
        await roster.confirm("0x279630", "Bad")
    await roster.handle(announce("0x279621", "Wohnzimmer"))
    with pytest.raises(NotAnnounced):
        await roster.confirm("0x279621", "Wohnzimmer 2")


async def test_confirm_refuses_a_name_in_use(roster: Roster) -> None:
    await roster.handle(announce("0x279630", "Küche"))
    with pytest.raises(NameTaken):
        await roster.confirm("0x279630", "küche")


async def test_confirm_refuses_a_bad_name_length(roster: Roster) -> None:
    await roster.handle(announce("0x279630", "Bad"))
    for name in ("", "   ", "x" * 41):
        with pytest.raises(ValueError):
            await roster.confirm("0x279630", name)


def test_start_builds_the_household_from_file_and_table(tmp_path) -> None:
    rows = RosterStore(tmp_path / "state.db")
    rows.insert("bad", "0x279630", "Bad")
    rows.insert("alt", "0x279640", "Alte Küche")
    rows.set_state("alt", "set_aside")
    settings = Settings.model_validate(CONFIG)
    roster = Roster(settings, rows)
    assert list(settings.shutters) == ["wohnzimmer", "kueche", "schlafzimmer", "bad"]
    assert [(a.address, a.name) for a in roster.set_aside()] == [("0x279640", "Alte Küche")]
    rows.close()


def test_file_wins_over_the_table(tmp_path, caplog) -> None:
    rows = RosterStore(tmp_path / "state.db")
    rows.insert("wohnen", "0x279621", "Wohnen")
    settings = Settings.model_validate(CONFIG)
    with caplog.at_level(logging.WARNING):
        Roster(settings, rows)
    assert [s.id for s in settings.shutter if s.address == "0x279621"] == ["wohnzimmer"]
    assert "0x279621" in caplog.text
    rows.close()


def test_start_with_no_configured_shutters(tmp_path) -> None:
    rows = RosterStore(tmp_path / "state.db")
    rows.insert("bad", "0x279630", "Bad")
    settings = Settings.model_validate({**CONFIG, "shutter": []})
    Roster(settings, rows)
    assert list(settings.shutters) == ["bad"]
    rows.close()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Gästezimmer", "gaestezimmer"),
        ("Bad oben", "bad-oben"),
        ("Küche/Süd", "kueche-sued"),
        ("Straße", "strasse"),
        ("  Öl!! ", "oel"),
        ("???", "rolladen"),
    ],
)
def test_slug(name: str, expected: str) -> None:
    assert slug(name, set()) == expected


def test_slug_suffixes_on_collision() -> None:
    assert slug("Bad", {"bad"}) == "bad-2"
    assert slug("Bad", {"bad", "bad-2"}) == "bad-3"


async def test_slug_avoids_configured_and_stored_ids(roster: Roster, rows: RosterStore) -> None:
    rows.insert("bad", "0x279699", "Altes Bad")
    rows.set_state("bad", "set_aside")
    await roster.handle(announce("0x279630", "Küche neu"))
    await roster.handle(announce("0x279631", "Bad"))
    first = await roster.confirm("0x279630", "Kueche")
    assert first.id == "kueche-2"
    second = await roster.confirm("0x279631", "Bad")
    assert second.id == "bad-2"


async def test_unique_name_suggestion(roster: Roster) -> None:
    assert roster.unique_name("Küche") == "Küche 2"
    assert roster.unique_name("Bad") == "Bad"
