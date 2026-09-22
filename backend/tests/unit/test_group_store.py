"""T007: groups, their members and both orders (feature 004, data-model.md)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from somfy_shutters.groups import GroupDraft, GroupStore, NameTaken, NotAPermutation


@pytest.fixture
def groups(tmp_path):
    store = GroupStore(tmp_path / "state.db")
    yield store
    store.close()


def draft(name: str, *members: str) -> GroupDraft:
    return GroupDraft(name=name, members=list(members))


def test_round_trip_keeps_member_order_and_survives_reopening(tmp_path) -> None:
    store = GroupStore(tmp_path / "state.db")
    made = store.create(draft("Obergeschoss", "schlafzimmer", "bad", "kind"))
    store.create(draft("Erdgeschoss", "kueche"))
    store.close()

    again = GroupStore(tmp_path / "state.db")
    assert [g.name for g in again.groups()] == ["Obergeschoss", "Erdgeschoss"]
    assert again.get(made.id).members == ["schlafzimmer", "bad", "kind"]
    again.close()


def test_a_shutter_can_be_in_several_groups(groups) -> None:
    groups.create(draft("Wohnzimmer", "wohnzimmer", "kueche"))
    groups.create(draft("Südseite", "wohnzimmer", "schlafzimmer"))
    assert [("wohnzimmer" in g.members) for g in groups.groups()] == [True, True]


def test_names_collide_ignoring_case_and_whitespace(groups) -> None:
    first = groups.create(draft("Südseite", "kueche"))
    with pytest.raises(NameTaken) as caught:
        groups.create(draft(" südseite ", "wohnzimmer"))
    assert caught.value.group_id == first.id


def test_decomposed_umlaut_is_the_same_name(groups) -> None:
    groups.create(draft("Küche", "kueche"))
    with pytest.raises(NameTaken):
        groups.create(draft("Küche", "kueche"))


def test_renaming_to_own_name_in_other_case_is_allowed(groups) -> None:
    made = groups.create(draft("wohnzimmer", "wohnzimmer"))
    renamed = groups.update(made.id, draft("Wohnzimmer", "wohnzimmer", "kueche"))
    assert renamed is not None and renamed.name == "Wohnzimmer"
    assert groups.get(made.id).members == ["wohnzimmer", "kueche"]


def test_renaming_onto_another_groups_name_is_refused(groups) -> None:
    groups.create(draft("Oben", "bad"))
    other = groups.create(draft("Unten", "kueche"))
    with pytest.raises(NameTaken):
        groups.update(other.id, draft("OBEN", "kueche"))
    assert groups.get(other.id).name == "Unten"


def test_update_of_a_missing_group_is_none(groups) -> None:
    assert groups.update("g_nope", draft("X", "kueche")) is None


def test_delete_removes_only_that_group(groups) -> None:
    a = groups.create(draft("A", "wohnzimmer", "kueche"))
    b = groups.create(draft("B", "wohnzimmer"))
    assert groups.delete(a.id) is True
    assert groups.get(a.id) is None
    assert groups.get(b.id).members == ["wohnzimmer"]
    assert groups.delete(a.id) is False


def test_new_groups_are_appended_and_reorder_is_kept(groups) -> None:
    a = groups.create(draft("A", "kueche"))
    b = groups.create(draft("B", "kueche"))
    c = groups.create(draft("C", "kueche"))
    assert [g.name for g in groups.reorder([c.id, a.id, b.id])] == ["C", "A", "B"]
    d = groups.create(draft("D", "kueche"))
    assert [g.id for g in groups.groups()] == [c.id, a.id, b.id, d.id]


@pytest.mark.parametrize("change", ["missing", "extra", "twice"])
def test_reorder_must_be_a_permutation(groups, change) -> None:
    a = groups.create(draft("A", "kueche"))
    b = groups.create(draft("B", "kueche"))
    ids = {"missing": [a.id], "extra": [a.id, b.id, "g_x"], "twice": [a.id, a.id]}[change]
    with pytest.raises(NotAPermutation):
        groups.reorder(ids)
    assert [g.id for g in groups.groups()] == [a.id, b.id]


def test_prune_drops_unconfigured_members_and_keeps_empty_groups(groups) -> None:
    mixed = groups.create(draft("Mixed", "wohnzimmer", "buero"))
    alone = groups.create(draft("Allein", "buero"))
    assert groups.prune(["wohnzimmer", "kueche"]) is True
    assert groups.get(mixed.id).members == ["wohnzimmer"]
    assert groups.get(alone.id).members == []
    assert groups.prune(["wohnzimmer", "kueche"]) is False


def test_a_pruned_shutter_readded_is_in_no_group(groups) -> None:
    made = groups.create(draft("Büro", "buero"))
    groups.prune(["kueche"])
    groups.prune(["kueche", "buero"])  # back in the configuration
    assert groups.get(made.id).members == []


def test_prune_with_nothing_configured_empties_every_group(groups) -> None:
    made = groups.create(draft("A", "kueche"))
    assert groups.prune([]) is True
    assert groups.get(made.id).members == []


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "members": ["kueche"]},
        {"name": "   ", "members": ["kueche"]},
        {"name": "x" * 41, "members": ["kueche"]},
        {"name": "A", "members": []},
        {"name": "A", "members": ["kueche", "kueche"]},
    ],
)
def test_draft_rejects(body) -> None:
    with pytest.raises(ValidationError):
        GroupDraft.model_validate(body)


def test_draft_accepts_forty_characters_after_trimming() -> None:
    assert GroupDraft(name="  " + "x" * 40 + "  ", members=["kueche"]).name == "x" * 40
