"""EventExplorer: the expanded event view (F02, UC02)."""

from datetime import date

import pytest
from conftest import ScriptedLLM

from praxis.agent.prompts import PromptBuilder
from praxis.documents import Book, NewsArticle
from praxis.llm import LLMError
from praxis.news.events import Event, Grouping
from praxis.news.exploration import NO_LIBRARY_CONTEXT, NO_LLM, UNCITED, EventExplorer
from praxis.persistence import Database, SQLDocumentRepository

TODAY = date(2026, 11, 22)


def report(title, outlet, text, day=TODAY):
    return NewsArticle(title=title, author="Staff", outlet=outlet, text=text, publication_date=day,
                       source_url=f"https://{outlet.replace(' ', '')}.example/{title.replace(' ', '-')}")


A = report("Dockworkers strike closes ports", "Wire A", "Dockworkers struck over wages; ports closed.")
B = report("Port strike spreads along the coast", "Wire B", "The dockworkers strike spread to three more ports.")
RELATED = report("Shipping firms warn of dockworkers strike losses", "Wire C", "Shipping firms said the strike costs millions.")
OLD = report("Dockworkers strike in 2025 ended", "Wire C", "An earlier dockworkers strike ended.", day=date(2026, 1, 5))
BOOK = Book(title="Value, Price and Profit", author="Marx", license="Public Domain",
            text="A general strike of the workers raises the question of wages and profit.")

EVENT = Event((A, B), Grouping.CONFIDENT, title="Dockworkers strike closes ports")

ACCOUNT = """\
## What happened
Dockworkers struck over wages [1] and the strike spread [2].

## Where the reports differ
Wire B reports three more ports [2]; Wire A does not say how many [1].

## Background from the library
Marx discusses strikes over wages and profit [3].

## Open questions
- How many workers are on strike?
- Will the employers negotiate?
"""


@pytest.fixture
def documents():
    database = Database()
    documents = SQLDocumentRepository(database)
    for document in (A, B, RELATED, OLD, BOOK):
        documents.save(document)
    yield documents
    database.close()


def explorer(documents, llm, today=TODAY):
    return EventExplorer(documents, llm, today=lambda: today)


def test_reports_come_first_then_library_passages(documents):
    llm = ScriptedLLM("strike, wages, profit", ACCOUNT)
    expanded = explorer(documents, llm).explore(EVENT)

    assert [s.citation.document_title for s in expanded.report_sources] == [A.title, B.title]
    assert [s.citation.document_title for s in expanded.library_sources] == ["Value, Price and Profit"]
    assert expanded.search_terms == ("strike", "wages", "profit")
    assert "[3] Marx, “Value, Price and Profit”, ¶1" in llm.prompts[1].user


def test_related_reports_are_nearby_in_time_and_not_already_in_the_event(documents):
    expanded = explorer(documents, None).explore(EVENT)
    assert [r.title for r in expanded.related] == [RELATED.title]


def test_the_account_is_split_from_its_open_questions(documents):
    expanded = explorer(documents, ScriptedLLM("strike, wages", ACCOUNT)).explore(EVENT)
    assert expanded.account.startswith("## What happened")
    assert "## Open questions" not in expanded.account
    assert expanded.open_questions == ("How many workers are on strike?", "Will the employers negotiate?")
    assert [s.number for s in expanded.cited] == [1, 2, 3]
    assert expanded.tokens_used == 30
    assert expanded.warnings == ()


def test_a_recent_event_is_developing(documents):
    llm = ScriptedLLM("strike", ACCOUNT)
    expanded = explorer(documents, llm).explore(EVENT)
    assert expanded.developing
    assert "may still be developing" in llm.prompts[1].user
    assert not explorer(documents, None, today=date(2026, 12, 1)).explore(EVENT).developing


def test_an_account_citing_no_report_is_flagged(documents):
    expanded = explorer(documents, ScriptedLLM("strike", "## What happened\nPorts closed.")).explore(EVENT)
    assert UNCITED in expanded.warnings


def test_citations_beyond_the_sources_are_flagged(documents):
    expanded = explorer(documents, ScriptedLLM("strike", "## What happened\nPorts closed [1] [9].")).explore(EVENT)
    assert any("[9], which is not among" in w for w in expanded.warnings)


def test_without_a_model_the_reports_and_passages_are_still_shown(documents):
    expanded = explorer(documents, None).explore(EVENT)
    assert expanded.account == ""
    assert NO_LLM in expanded.warnings
    assert expanded.library_sources  # found from the headlines


def test_model_failure_keeps_the_material(documents):
    expanded = explorer(documents, ScriptedLLM("strike", LLMError("timeout"))).explore(EVENT)
    assert expanded.report_sources
    assert any("timeout" in w for w in expanded.warnings)


def test_no_library_context_is_reported(documents):
    lone = report("Election results announced", "Wire D", "The count finished overnight.")
    documents.save(lone)
    expanded = explorer(documents, None).explore(Event((lone,), Grouping.SINGLE_REPORT))
    assert NO_LIBRARY_CONTEXT in expanded.warnings


def test_a_report_without_a_summary_is_cited_by_its_headline(documents):
    bare = report("Ports reopen", "Wire E", "")
    documents.save(bare)
    expanded = explorer(documents, None).explore(Event((bare,), Grouping.SINGLE_REPORT))
    assert expanded.report_sources[0].citation.quoted_text == "Ports reopen"


def test_exploration_prompt_rules():
    prompt = PromptBuilder().build_event_exploration_prompt(
        "Strike", [("[1]", "Wire A", "2026-11-22", "Strike", "")], [],
    )
    assert "do not decide which is right" in prompt.system
    assert "(no summary in the feed)" in prompt.user
    assert "No library passages were found" in prompt.user
