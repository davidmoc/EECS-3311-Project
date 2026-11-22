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


# --- saved answers (F04 + F15) ----------------------------------------------


def answer(question="Why do wages fall?", explanation="Competition [1]."):
    from praxis.agent import AgentResponse, ResearchCorpus, ResponseStatus

    document = Book(title="Manifesto", author="Marx", text="Wages fall.", license="Public domain")
    source = ResearchCorpus().add_passage(document, document.passages()[0])
    return AgentResponse(
        question, ResponseStatus.ANSWERED, (source,), explanation, (source,),
        warnings=("A warning.",),
    )


def test_answer_is_saved_with_its_sources(service):
    item = service.save_answer(answer(), tags=("wages",))

    assert item.kind is SavedItemKind.RESEARCH
    assert item.title == "Q: Why do wages fall?"
    assert item.tags == ("wages",)
    assert item.content == (
        "Explanation (AI-generated):\nCompetition [1].\n\n"
        "Sources:\n[1] Marx, “Manifesto”, ¶1\nWages fall.\n\n"
        "Note: A warning."
    )
    assert service.search("competition") == [item]


def test_saving_the_same_question_again_replaces_the_answer(service):
    first = service.save_answer(answer())
    second = service.save_answer(answer("why  do WAGES fall?", "Supply [1]."))

    assert second.id == first.id
    assert len(service.get_workspace().items) == 1
    assert "Supply [1]." in second.content


def test_research_results_are_saved_with_a_session_reference():
    from praxis.agent import ResponseStatus
    from praxis.research import ResearchSession
    from praxis.research.result import ResearchResult
    from praxis.workspace.service import render_research

    session = ResearchSession("Why did 1848 fail?")
    result = ResearchResult(session, ResponseStatus.NO_SOURCES, None)
    service = WorkspaceService(SQLWorkspaceRepository(Database()))

    item = service.save_research(result, tags=("1848",))

    assert item.title == "Research: Why did 1848 fail?"
    assert service.research_session_of(item) == session.id
    assert render_research(result).startswith("This research is incomplete.")
    assert service.research_session_of(service.add_note("x")) is None
