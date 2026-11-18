from datetime import datetime
from uuid import UUID

import pytest

from praxis.documents import Book
from praxis.persistence import Database, SQLWorkspaceRepository
from praxis.workspace import SavedItemKind
from praxis.workspace.service import WorkspaceError, WorkspaceService

NOW = datetime(2026, 11, 18, 15, 0)


@pytest.fixture
def database():
    database = Database()
    yield database
    database.close()


@pytest.fixture
def service(database):
    return WorkspaceService(SQLWorkspaceRepository(database), clock=lambda: NOW)


def manifesto(license="Public domain"):
    return Book(
        title="Manifesto",
        author="Marx",
        text="Intro.\n\n" + "The history of all hitherto existing societies. " * 20,
        license=license,
        source_url="https://example.org/61",
        topics=("class struggle",),
    )


def test_items_round_trip_through_the_database(database, service):
    service.add_note("Question", "Why 1848?", tags=("History",))

    [item] = SQLWorkspaceRepository(database).load().items
    assert (item.title, item.content, item.tags, item.saved_at) == (
        "Question", "Why 1848?", ("history",), NOW,
    )


def test_saved_document_keeps_source_and_topics_and_can_be_reopened(service):
    book = manifesto()

    item = service.save_document(book, note="start here")

    assert item.kind is SavedItemKind.DOCUMENT
    assert item.content == "https://example.org/61"
    assert item.tags == ("class struggle",)
    assert service.document_id_of(item) == book.id
    assert service.paragraph_of(item) is None


def test_saved_passage_keeps_citation_and_location(service):
    book = manifesto()
    passage = book.passages()[1]

    item = service.save_passage(book, passage)

    assert item.title == "Marx, “Manifesto”, ¶2"
    assert item.content == passage.text
    assert service.document_id_of(item) == book.id
    assert service.paragraph_of(item) == 2


def test_passage_from_restricted_text_is_saved_as_excerpt_only(service):
    book = manifesto(license="All rights reserved")

    item = service.save_passage(book, book.passages()[1])

    assert item.content.endswith("…")
    assert len(item.content) < len(book.passages()[1].text)


def test_saving_twice_does_not_duplicate(service):
    book = manifesto()
    service.save_document(book)
    service.save_document(book, note="again")

    [item] = service.get_workspace().items
    assert item.note == "again"


def test_remove_by_prefix(service):
    item = service.add_note("Temporary")

    removed = service.remove_item(str(item.id)[:6])

    assert removed.id == item.id
    assert service.get_workspace().items == []


@pytest.mark.parametrize("bad", ["", "zzzz"])
def test_unknown_item_id_is_an_error(service, bad):
    with pytest.raises(WorkspaceError):
        service.get_item(bad)


def test_note_has_no_document_to_reopen(service):
    assert service.document_id_of(service.add_note("n")) is None


def test_search_finds_saved_items(service):
    service.save_document(manifesto())
    service.add_note("Unrelated")

    assert [i.kind for i in service.search("class struggle")] == [SavedItemKind.DOCUMENT]
