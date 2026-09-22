"""T025: who a rule reaches, with groups (feature 004, data-model.md "Resolution")."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from somfy_shutters.automation.models import RuleDraft, Targets
from somfy_shutters.automation.planner import next_firing
from somfy_shutters.automation.targets import resolve
from somfy_shutters.groups import Group

BERLIN = ZoneInfo("Europe/Berlin")
CONFIGURED = ["wohnzimmer", "kueche", "schlafzimmer", "buero"]
EG = Group(id="g_eg", name="Erdgeschoss", members=["kueche", "wohnzimmer"])
SUED = Group(id="g_sued", name="Südseite", members=["wohnzimmer", "schlafzimmer"])
GROUPS = [EG, SUED]


def t(shutters=(), groups=()) -> Targets:
    return Targets(shutters=list(shutters), groups=list(groups))


def test_all_is_every_configured_shutter_and_no_group() -> None:
    got = resolve("all", CONFIGURED, GROUPS)
    assert got.reached == CONFIGURED
    assert got.via == {} and got.removed == []


def test_one_group_is_its_members_in_configuration_order() -> None:
    got = resolve(t(groups=["g_eg"]), CONFIGURED, GROUPS)
    assert got.reached == ["wohnzimmer", "kueche"]  # not the group's own order
    assert got.via == {"wohnzimmer": ["Erdgeschoss"], "kueche": ["Erdgeschoss"]}


def test_two_groups_sharing_a_shutter_reach_it_once_through_both() -> None:
    got = resolve(t(groups=["g_eg", "g_sued"]), CONFIGURED, GROUPS)
    assert got.reached == ["wohnzimmer", "kueche", "schlafzimmer"]
    assert got.via["wohnzimmer"] == ["Erdgeschoss", "Südseite"]


def test_group_plus_a_direct_shutter() -> None:
    got = resolve(t(shutters=["buero", "kueche"], groups=["g_sued"]), CONFIGURED, GROUPS)
    assert got.reached == ["wohnzimmer", "kueche", "schlafzimmer", "buero"]
    assert "buero" not in got.via and "kueche" not in got.via


def test_membership_is_read_at_the_call() -> None:
    grown = Group(id="g_eg", name="Erdgeschoss", members=["kueche", "wohnzimmer", "buero"])
    assert "buero" in resolve(t(groups=["g_eg"]), CONFIGURED, [grown]).reached


def test_unknown_group_is_ignored() -> None:
    got = resolve(t(shutters=["kueche"], groups=["g_gone"]), CONFIGURED, GROUPS)
    assert got.reached == ["kueche"] and got.removed == []


def test_direct_shutter_no_longer_configured_is_removed() -> None:
    got = resolve(t(shutters=["kueche", "keller"]), CONFIGURED, GROUPS)
    assert got.reached == ["kueche"] and got.removed == ["keller"]


def test_nothing_left_means_no_targets() -> None:
    draft = RuleDraft.model_validate(
        {
            "name": "x",
            "days": [True] * 7,
            "trigger": {"kind": "time", "time": "06:45"},
            "targets": {"groups": ["g_gone"]},
            "action": {"kind": "open"},
        }
    )
    got = resolve(draft.targets, CONFIGURED, GROUPS)
    assert got.reached == []
    nxt = next_firing(
        draft, datetime(2026, 9, 22, 6, 0, tzinfo=BERLIN), BERLIN, None, has_targets=False
    )
    assert nxt.reason == "no_targets"


def test_legacy_plain_list_reads_as_shutters() -> None:
    draft = RuleDraft.model_validate(
        {
            "name": "alt",
            "days": [True] * 7,
            "trigger": {"kind": "time", "time": "06:45"},
            "targets": ["kueche", "wohnzimmer"],
            "action": {"kind": "open"},
        }
    )
    assert draft.targets == Targets(shutters=["kueche", "wohnzimmer"], groups=[])
