"""PoliticalResearchAgent.explore_history (F09, UC09)."""

from datetime import date

import pytest
from conftest import ScriptedLLM

from praxis.agent import AgentError, PoliticalResearchAgent
from praxis.agent.agent import HISTORY_PLAN_UNUSABLE, HISTORY_UNREADABLE, NO_HISTORY_SOURCES, NO_LLM_WARNING
from praxis.documents import NewsArticle
from praxis.llm import LLMError
from praxis.news.events import Event, Grouping
from praxis.persistence import SQLDocumentRepository, SQLReaderProfileRepository
from praxis.reader_model.service import ReaderProfileService
from praxis.research.history import ContextStatus, HistoryItemKind
from praxis.tools import PassageSearchTool, ToolManager


def make_agent(database, llm):
    tools = ToolManager()
    tools.register_tool(PassageSearchTool(SQLDocumentRepository(database)))
    return PoliticalResearchAgent(tools, ReaderProfileService(SQLReaderProfileRepository(database)), llm)


PLAN = "scope: focused |\nsearch: the revolution | revolution Paris Germany\nsearch: the barricades | barricades Vienna Berlin"
# The searches find, in order: [1] the Revolution text's ¶1, [2] its ¶2 (the
# barricades), then the topic as typed adds the Manifesto's ¶3 as [3].
ACCOUNT = """\
overview: The revolution spread to Germany, where the bourgeoisie made peace with the monarchy [1, 2].
stage: 1848 | The revolution broke out in Paris and spread across Germany [1].
turning point: undated | The bourgeoisie made peace with the monarchy [1].
interpretation: Engels holds that the liberals feared the workers more than the old order [2].
origin: An unsupported claim [7].
gap: Nothing on the peasants.
"""


def test_history_is_planned_retrieved_and_organised(library_database):
    llm = ScriptedLLM(PLAN, ACCOUNT)
    context = make_agent(library_database, llm).explore_history("the bourgeoisie in 1848")

    assert context.status is ContextStatus.EXPLAINED
    assert context.steps[0] == "the revolution: revolution Paris Germany  +1 source"
    assert context.steps[-1].startswith("the topic as asked: the bourgeoisie in 1848")
    assert all(context.purposes[s.number] == "history" for s in context.sources)
    assert context.overview.startswith("The revolution spread to Germany")
    stage = context.of_kind(HistoryItemKind.STAGE)[0]
    assert (stage.when, stage.evidence) == ("1848", (1,))
    assert context.of_kind(HistoryItemKind.INTERPRETATION)[0].text.startswith("Engels holds")
    assert context.gaps == ("Nothing on the peasants.",)
    assert context.tokens_used == 30
    assert "Topic: the bourgeoisie in 1848" in llm.prompts[1].user


def test_items_citing_no_retrieved_passage_are_left_out(library_database):
    context = make_agent(library_database, ScriptedLLM(PLAN, ACCOUNT)).explore_history("1848")

    assert context.of_kind(HistoryItemKind.ORIGIN) == []
    assert "1 item of the account cited no retrieved passage and was left out." in context.warnings


def test_suggested_readings_are_the_texts_cited(library_database):
    context = make_agent(library_database, ScriptedLLM(PLAN, ACCOUNT)).explore_history("1848")

    assert [(r.title, r.cited, r.start) for r in context.readings] == [
        ("Revolution and Counter-Revolution in Germany", 2, "¶1"),
    ]
    assert {s.number for s in context.cited} == {1, 2}


def test_a_too_broad_topic_asks_to_narrow_without_searching(library_database):
    llm = ScriptedLLM("scope: too broad | the 1848 revolutions; the Paris Commune")
    context = make_agent(library_database, llm).explore_history("the history of capitalism")

    assert context.status is ContextStatus.TOO_BROAD
    assert context.narrower == ("the 1848 revolutions", "the Paris Commune")
    assert context.sources == ()
    assert len(llm.prompts) == 1


def test_a_broad_topic_can_be_traced_anyway(library_database):
    llm = ScriptedLLM("scope: too broad | 1848", ACCOUNT)
    context = make_agent(library_database, llm).explore_history("revolution", allow_broad=True)

    assert context.status is ContextStatus.EXPLAINED
    assert context.steps == ("the topic as asked: revolution  +1 source",)


def test_an_unusable_plan_searches_the_topic_as_typed(library_database):
    llm = ScriptedLLM(LLMError("timeout"), "stage: 1848 | The revolution broke out [1].")
    context = make_agent(library_database, llm).explore_history("revolution")

    assert HISTORY_PLAN_UNUSABLE in context.warnings
    assert len(context.steps) == 1
    assert context.status is ContextStatus.EXPLAINED


def test_without_a_model_the_passages_are_still_returned(library_database):
    context = make_agent(library_database, None).explore_history("revolution")

    assert context.status is ContextStatus.NOT_ORGANISED
    assert len(context.sources) == 1
    assert NO_LLM_WARNING in context.warnings


def test_an_unreadable_account_keeps_the_passages(library_database):
    context = make_agent(library_database, ScriptedLLM(PLAN, "It is complicated.")).explore_history("1848")

    assert context.status is ContextStatus.NOT_ORGANISED
    assert context.sources
    assert HISTORY_UNREADABLE in context.warnings


def test_an_account_citing_nothing_retrieved_is_not_shown(library_database):
    context = make_agent(library_database, ScriptedLLM(PLAN, "origin: something [9]")).explore_history("1848")

    assert context.status is ContextStatus.NOT_ORGANISED
    assert context.items == ()


def test_no_passages_means_no_account(library_database):
    llm = ScriptedLLM("scope: focused |\nsearch: x | xylophone")
    context = make_agent(library_database, llm).explore_history("xylophone")

    assert context.status is ContextStatus.NO_SOURCES
    assert NO_HISTORY_SOURCES in context.warnings
    assert len(llm.prompts) == 1


def test_an_event_starts_from_its_reports_which_are_not_suggested_readings(library_database):
    event = Event((NewsArticle(
        title="Barricades in Berlin again", author="Staff", outlet="a",
        text="Workers built barricades in Berlin over wages.", publication_date=date(2026, 11, 22),
    ),), Grouping.SINGLE_REPORT)
    llm = ScriptedLLM(
        "scope: focused |\nsearch: barricades | barricades Vienna Berlin",
        "stage: 1848 | Workers fought on the barricades [2], as they do now [1].",
    )
    context = make_agent(library_database, llm).explore_event_history(event)

    assert context.topic == "the historical background of: Barricades in Berlin again"
    assert context.purposes[1] == "event"
    assert context.steps[0] == "Start from the event's news reports  +1 source"
    assert [r.title for r in context.readings] == ["Revolution and Counter-Revolution in Germany"]


def test_an_empty_topic_is_refused(library_database):
    with pytest.raises(AgentError):
        make_agent(library_database, None).explore_history("  ")
