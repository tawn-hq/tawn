"""Listing, editing and deleting personal notes."""

import pytest

from tawn.memory.note import note
from tawn.memory.notes import delete_note, get_note, list_notes, update_note


@pytest.fixture()
def home(tmp_path):
    return tmp_path


def test_written_note_is_listed_with_an_id(home):
    note("First thought about routing.", home=home)
    notes = list_notes(home)
    assert len(notes) == 1
    assert notes[0]["body"] == "First thought about routing."
    assert notes[0]["note_id"]


def test_multiple_notes_in_one_day_are_separate(home):
    note("First.", home=home)
    note("Second.", home=home, domain="work")
    bodies = [n["body"] for n in list_notes(home)]
    assert "First." in bodies and "Second." in bodies


def test_filter_by_domain(home):
    note("Work thing.", home=home, domain="work")
    note("Money thing.", home=home, domain="wealth")
    assert [n["body"] for n in list_notes(home, domain="wealth")] == ["Money thing."]


def test_update_note_body(home):
    note("Original text.", home=home)
    nid = list_notes(home)[0]["id"]

    updated = update_note(home, nid, body="Revised text.")
    assert updated["body"] == "Revised text."
    assert [n["body"] for n in list_notes(home)] == ["Revised text."]


def test_update_preserves_other_notes(home):
    note("Keep me.", home=home)
    note("Change me.", home=home)
    target = next(n for n in list_notes(home) if n["body"] == "Change me.")

    update_note(home, target["id"], body="Changed.")
    bodies = {n["body"] for n in list_notes(home)}
    assert bodies == {"Keep me.", "Changed."}


def test_update_can_set_domain(home):
    note("Needs a domain.", home=home)
    nid = list_notes(home)[0]["id"]
    update_note(home, nid, domain="research")
    assert list_notes(home)[0]["domain"] == "research"


def test_update_unknown_note_returns_none(home):
    assert update_note(home, "nope", body="x") is None


def test_delete_note(home):
    note("Delete me.", home=home)
    note("Keep me.", home=home)
    target = next(n for n in list_notes(home) if n["body"] == "Delete me.")

    assert delete_note(home, target["id"]) is True
    assert [n["body"] for n in list_notes(home)] == ["Keep me."]


def test_delete_unknown_returns_false(home):
    assert delete_note(home, "nope") is False


def test_get_note_by_id(home):
    note("Findable.", home=home)
    nid = list_notes(home)[0]["id"]
    assert get_note(home, nid)["body"] == "Findable."


def test_empty_when_no_notes(home):
    assert list_notes(home) == []
