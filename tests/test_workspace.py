from datetime import datetime, timedelta

import pytest

from praxis.workspace import SavedItem, SavedItemKind, Workspace

T0 = datetime(2026, 11, 18, 10, 0)


def item(title="Manifesto", kind=SavedItemKind.DOCUMENT, reference="doc-1", **extra):
    return SavedItem(kind=kind, title=title, reference=reference, saved_at=extra.pop("saved_at", T0), **extra)


def test_item_needs_a_title():
    with pytest.raises(ValueError):
        SavedItem(kind=SavedItemKind.NOTE, title="  ")


def test_tags_are_normalized_and_deduplicated():
    assert item(tags=("State", " state", "", "Labour")).tags == ("labour", "state")


def test_saving_the_same_original_twice_updates_instead_of_duplicating():
    workspace = Workspace()
    first = workspace.add(item(tags=("a",)))

    second = workspace.add(item(note="Read chapter 2", tags=("b",)))

    assert second is first
    assert len(workspace.items) == 1
    assert first.note == "Read chapter 2"
    assert first.tags == ("a", "b")


def test_resaving_without_a_note_keeps_the_old_note():
    workspace = Workspace()
    workspace.add(item(note="keep me"))

    assert workspace.add(item()).note == "keep me"


def test_notes_without_reference_are_never_merged():
    workspace = Workspace()
    workspace.add(SavedItem(SavedItemKind.NOTE, "Idea"))
    workspace.add(SavedItem(SavedItemKind.NOTE, "Idea"))

    assert len(workspace.items) == 2


def test_same_reference_with_different_kind_is_a_different_item():
    workspace = Workspace()
    workspace.add(item(kind=SavedItemKind.DOCUMENT))
    workspace.add(item(kind=SavedItemKind.PASSAGE))

    assert len(workspace.items) == 2


def test_remove_returns_the_removed_item_or_none():
    workspace = Workspace()
    saved = workspace.add(item())

    assert workspace.remove(saved.id) is saved
    assert workspace.remove(saved.id) is None


def test_search_covers_title_content_note_and_tags_newest_first():
    workspace = Workspace()
    workspace.add(item("Old", reference="1", content="class struggle", saved_at=T0))
    workspace.add(item("New", reference="2", note="about class", tags=("struggle",), saved_at=T0 + timedelta(1)))
    workspace.add(item("Other", reference="3", saved_at=T0))

    assert [i.title for i in workspace.search("class struggle")] == ["New", "Old"]
    assert workspace.search("") == []


def test_newest_first_can_filter_by_kind():
    workspace = Workspace()
    workspace.add(item("Doc", reference="1"))
    workspace.add(item("Note", kind=SavedItemKind.NOTE, reference=""))

    assert [i.title for i in workspace.newest_first(SavedItemKind.NOTE)] == ["Note"]
