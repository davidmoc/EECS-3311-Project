"""Searching one document's passages, and SourceRetrievalTool (F10, SD06)."""

from uuid import uuid4

import pytest

from praxis.documents import Book
from praxis.persistence import Database, SQLDocumentRepository
from praxis.tools import SourceRetrievalTool

STATE_A = "The executive of the modern state is but a committee of the bourgeoisie."
STATE_B = "The state is an organ of class rule, an organ for the oppression of one class by another."
WAGES = "The average price of wage labour is the minimum wage of the labourer."


@pytest.fixture
def repository():
    database = Database()
    yield SQLDocumentRepository(database)
    database.close()


@pytest.fixture
def books(repository):
    manifesto = Book(title="Manifesto", author="Marx", text=f"{STATE_A}\n\n{WAGES}", license="Public Domain")
    lenin = Book(title="State and Revolution", author="Lenin", text=STATE_B, license="Public Domain")
    repository.save(manifesto)
    repository.save(lenin)
    return manifesto, lenin


def test_passage_search_can_be_limited_to_one_document(repository, books):
    manifesto, lenin = books
    everywhere = repository.search_passages("state class")
    assert {m.document.id for m in everywhere} == {manifesto.id, lenin.id}

    only_lenin = repository.search_passages("state class", document_id=lenin.id)
    assert [m.passage.text for m in only_lenin] == [STATE_B]


def test_tool_finds_the_sources_passages_on_the_subject(repository, books):
    manifesto, _ = books
    result = SourceRetrievalTool(repository).execute(
        {"document_id": str(manifesto.id), "query": "the state"}
    )
    assert result.success
    assert [m.passage.text for m in result.items] == [STATE_A]


def test_tool_returns_named_paragraphs_in_the_order_given(repository, books):
    manifesto, _ = books
    result = SourceRetrievalTool(repository).execute(
        {"document_id": str(manifesto.id), "paragraphs": [2, 1, 2]}
    )
    assert result.success
    assert [m.passage.locator for m in result.items] == ["¶2", "¶1"]
    assert result.items[0].document.title == "Manifesto"


def test_tool_reports_a_missing_paragraph(repository, books):
    manifesto, _ = books
    result = SourceRetrievalTool(repository).execute(
        {"document_id": str(manifesto.id), "paragraphs": [1, 9]}
    )
    assert not result.success
    assert "there is no ¶9" in result.error


def test_tool_reports_an_unknown_document(repository, books):
    result = SourceRetrievalTool(repository).execute({"document_id": str(uuid4()), "query": "state"})
    assert not result.success
    assert "No source" in result.error


@pytest.mark.parametrize(
    "tool_input",
    [
        {"query": "state"},
        {"document_id": "not-a-uuid", "query": "state"},
        {"document_id": str(uuid4())},
        {"document_id": str(uuid4()), "query": "  "},
        {"document_id": str(uuid4()), "paragraphs": []},
        {"document_id": str(uuid4()), "paragraphs": [0]},
        {"document_id": str(uuid4()), "paragraphs": [True]},
        {"document_id": str(uuid4()), "query": "state", "limit": 0},
        {"document_id": str(uuid4()), "query": "state", "limit": 99},
    ],
)
def test_tool_rejects_invalid_input(repository, tool_input):
    assert SourceRetrievalTool(repository).validate(tool_input) is False
