from uuid import uuid4

import pytest

from praxis.agent import AgentResponse, ResearchCorpus, ResponseStatus
from praxis.documents import Book, Citation
from praxis.documents.models import EXCERPT_LIMIT


def book(text, license="Public Domain"):
    return Book(title="Capital", author="Karl Marx", text=text, license=license)


def test_sources_are_numbered_in_the_order_added():
    document = book("First paragraph.\n\nSecond paragraph.")
    first, second = document.passages()
    corpus = ResearchCorpus()

    a = corpus.add_passage(document, second)
    b = corpus.add_passage(document, first)

    assert (a.number, b.number) == (1, 2)
    assert a.label == "[1]"
    assert corpus.source(2).passage == first
    assert a.citation.locator == "¶2"
    assert corpus.documents == [document]


def test_adding_a_passage_twice_keeps_its_number():
    document = book("Only paragraph.")
    [passage] = document.passages()
    corpus = ResearchCorpus()

    corpus.add_passage(document, passage)
    again = corpus.add_passage(document, passage)

    assert again.number == 1
    assert len(corpus) == 1


def test_citations_respect_the_licence_quotation_limit():
    document = book("x" * (EXCERPT_LIMIT + 100), license="All rights reserved")
    [passage] = document.passages()

    source = ResearchCorpus().add_passage(document, passage)

    assert len(source.citation.quoted_text) <= EXCERPT_LIMIT + 1


def test_citation_for_another_document_is_rejected():
    document = book("Paragraph.")
    [passage] = document.passages()
    wrong = Citation(uuid4(), "Other", "Someone", "¶1", "text")

    with pytest.raises(ValueError):
        ResearchCorpus().add_citation(passage, wrong)


def test_unknown_source_numbers():
    corpus = ResearchCorpus()

    assert corpus.is_empty
    assert not corpus.has_source(1)
    with pytest.raises(KeyError):
        corpus.source(1)


def test_response_is_grounded_only_when_the_answer_cites_a_source():
    document = book("Paragraph.")
    source = ResearchCorpus().add_passage(document, document.passages()[0])

    cited = AgentResponse("q", ResponseStatus.ANSWERED, (source,), "x [1]", (source,))
    uncited = AgentResponse("q", ResponseStatus.ANSWERED, (source,), "x", ())
    empty = AgentResponse("q", ResponseStatus.NO_SOURCES)

    assert cited.is_grounded
    assert not uncited.is_grounded
    assert not empty.is_grounded
