"""PoliticalResearchAgent.research_event (F02, SD03's researchEvent)."""

from datetime import date

from conftest import ScriptedLLM

from praxis.agent import PoliticalResearchAgent
from praxis.agent.agent import EVENT_QUESTION
from praxis.documents import NewsArticle
from praxis.news.events import Event, Grouping
from praxis.persistence import SQLDocumentRepository, SQLReaderProfileRepository
from praxis.persistence.research import SQLResearchRepository
from praxis.reader_model.service import ReaderProfileService
from praxis.tools import ToolFactory, ToolManager


def report(title, outlet, text):
    return NewsArticle(title=title, author="Staff", outlet=outlet, text=text,
                       publication_date=date(2026, 11, 22), source_url=f"https://{outlet}.example/x")


EVENT = Event((
    report("Dockworkers strike closes ports", "a", "Dockworkers struck over wages and the ports closed."),
    report("Port strike spreads", "b", "The strike spread to three more ports along the coast."),
), Grouping.CONFIDENT, title="Dockworkers strike closes ports")


def agent_for(database, llm):
    documents = SQLDocumentRepository(database)
    for r in EVENT.reports:
        documents.save(r)
    tools = ToolManager()
    for tool in ToolFactory(documents).create_all():
        tools.register_tool(tool)
    return PoliticalResearchAgent(
        tools, ReaderProfileService(SQLReaderProfileRepository(database)), llm,
        research_repository=SQLResearchRepository(database),
    )


def test_research_on_an_event_starts_from_its_reports(library_database):
    llm = ScriptedLLM(
        "evidence: bourgeoisie wage labour",
        "verdict: sufficient",
        "## Findings\nDockworkers struck over wages [1], as the Manifesto describes [3].",
    )
    result = agent_for(library_database, llm).research_event(EVENT)

    assert result.objective == EVENT_QUESTION.format(headline="Dockworkers strike closes ports")
    first = result.session.steps[0]
    assert first.description == "Start from the event's 2 news reports"
    assert first.new_sources == (1, 2)
    assert [s.citation.document_title for s in result.sources[:2]] == [r.title for r in EVENT.reports]
    assert result.purposes[1] == "event"
    # The reports are in the synthesis prompt under their own heading.
    assert "### News reports of the event being researched" in llm.prompts[-1].user
    assert len(result.sources) > 2  # the plan's library search still ran


def test_event_research_is_stored_like_any_research(library_database):
    llm = ScriptedLLM("evidence: wage labour", "verdict: sufficient", "## Findings\nWages [1].")
    agent = agent_for(library_database, llm)
    result = agent.research_event(EVENT)
    assert agent.get_research(result.session.id).purposes[1] == "event"
