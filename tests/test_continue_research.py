"""PoliticalResearchAgent.continue_research and session storage (F03, UC15)."""

import sqlite3

import pytest
from conftest import ScriptedLLM

from praxis.agent import AgentError, PoliticalResearchAgent, ResponseStatus
from praxis.agent.agent import NOTHING_TO_CONTINUE
from praxis.persistence import SQLDocumentRepository, SQLReaderProfileRepository
from praxis.persistence.research import SQLResearchRepository
from praxis.reader_model.service import ReaderProfileService
from praxis.research import ResearchBudget, ResearchStatus
from praxis.research.planner import FALLBACK_FOLLOW_UP_WARNING
from praxis.research.policy import StopReason
from praxis.tools import PassageSearchTool, ToolManager

OBJECTIVE = "Why did the German revolution of 1848 fail?"
PLAN = "history: 1848 revolution Germany\ntheory: bourgeoisie state"
SUFFICIENT = "development: The bourgeoisie turned against the revolution [1]\nverdict: sufficient"
SYNTHESIS = "## Findings\nThe bourgeoisie made peace with the monarchy [1].\n"
FOCUS = "wage labour"
FOLLOW_UP_PLAN = "theory: wage labour subsistence"


def make_agent(database, llm, repository=None):
    tools = ToolManager()
    tools.register_tool(PassageSearchTool(SQLDocumentRepository(database)))
    profiles = ReaderProfileService(SQLReaderProfileRepository(database))
    repository = repository or SQLResearchRepository(database)
    return PoliticalResearchAgent(tools, profiles, llm, research_repository=repository)


def first_round(database, *replies, budget=None):
    return make_agent(database, ScriptedLLM(*replies)).research(OBJECTIVE, budget)


def test_research_is_stored_and_can_be_reopened(library_database):
    result = first_round(library_database, PLAN, SUFFICIENT, SYNTHESIS)
    agent = make_agent(library_database, None)

    session_id = agent.find_research(str(result.session.id)[:8])

    assert session_id == result.session.id
    assert agent.get_research(session_id) == result


def test_continuing_with_a_focus_keeps_earlier_sources_and_adds_new_ones(library_database):
    first = first_round(library_database, PLAN, SUFFICIENT, SYNTHESIS)
    llm = ScriptedLLM(FOLLOW_UP_PLAN, SUFFICIENT, SYNTHESIS)

    second = make_agent(library_database, llm).continue_research(first.session.id, FOCUS)

    session = second.session
    assert session.id == first.session.id and session.rounds == 2
    assert session.status is ResearchStatus.COMPLETED
    assert session.focuses == {2: FOCUS}
    # Earlier sources keep their numbers; the round adds after them.
    assert second.sources[: len(first.sources)] == first.sources
    assert len(second.sources) > len(first.sources)
    new_steps = [s.description for s in session.steps if s.round == 2]
    assert new_steps[:2] == ["Retrieve theory: wage labour subsistence", f"Retrieve evidence: {FOCUS}"]
    # The follow-up plan prompt names the focus; the synthesis sees it too.
    assert FOCUS in llm.prompts[0].user and "already been researched" in llm.prompts[0].user
    assert "Follow-up directions from the reader:\n- wage labour" in llm.prompts[-1].user
    assert second.status is ResponseStatus.ANSWERED
    # The stored session is now the continued one.
    assert make_agent(library_database, None).get_research(session.id) == second


def test_continuing_runs_the_steps_a_limit_left_unrun(library_database):
    first = first_round(library_database, PLAN, SYNTHESIS, budget=ResearchBudget(max_tool_calls=1))
    assert first.is_incomplete
    llm = ScriptedLLM(SUFFICIENT, SYNTHESIS)

    second = make_agent(library_database, llm).continue_research(first.session.id)

    round_two = [s.description for s in second.session.steps if s.round == 2]
    assert round_two[:2] == ["Retrieve theory: bourgeoisie state", f"Retrieve evidence: {OBJECTIVE}"]
    assert not second.is_incomplete
    assert second.stop_reason is StopReason.SUFFICIENT
    # The budget is per round: the first round's tool call does not count.
    assert second.session.round_tool_call_count == 2
    assert not any("stopped early" in w for w in second.warnings)


def test_a_continuation_never_repeats_an_earlier_search(library_database):
    first = first_round(library_database, PLAN, SUFFICIENT, SYNTHESIS)
    llm = ScriptedLLM("history: 1848 revolution Germany", SUFFICIENT, SYNTHESIS)

    second = make_agent(library_database, llm).continue_research(
        first.session.id, "1848 revolution Germany"
    )

    descriptions = [s.description for s in second.session.steps if not s.is_assessment]
    assert descriptions.count("Trace historical development: 1848 revolution Germany") == 1


def test_without_a_model_the_focus_is_searched_as_given(library_database):
    first = first_round(library_database, PLAN, SUFFICIENT, SYNTHESIS)

    second = make_agent(library_database, None).continue_research(first.session.id, FOCUS)

    assert [s.description for s in second.session.steps if s.round == 2] == [
        f"Retrieve evidence: {FOCUS}"
    ]
    assert FALLBACK_FOLLOW_UP_WARNING in second.warnings
    assert second.status is ResponseStatus.EXPLANATION_FAILED


def test_nothing_to_continue_without_a_focus_is_refused(library_database):
    first = first_round(library_database, PLAN, "verdict: sufficient", SYNTHESIS)

    with pytest.raises(AgentError, match="no unfinished steps"):
        make_agent(library_database, None).continue_research(first.session.id)
    assert NOTHING_TO_CONTINUE.startswith("This research")


def test_unknown_or_ambiguous_sessions_are_reported(library_database):
    agent = make_agent(library_database, None)

    with pytest.raises(AgentError, match="No research session"):
        agent.find_research("abc")
    with pytest.raises(AgentError, match="required"):
        agent.find_research("  ")


def test_without_a_repository_research_still_works_but_cannot_be_continued(library_database):
    tools = ToolManager()
    tools.register_tool(PassageSearchTool(SQLDocumentRepository(library_database)))
    agent = PoliticalResearchAgent(
        tools, ReaderProfileService(SQLReaderProfileRepository(library_database)), None
    )

    result = agent.research(OBJECTIVE)

    assert result.sources
    with pytest.raises(AgentError, match="not being stored"):
        agent.continue_research(result.session.id, FOCUS)


class BrokenRepository(SQLResearchRepository):
    def save(self, result):
        raise sqlite3.OperationalError("database is locked")


def test_a_failed_save_is_reported_but_the_result_is_kept(library_database):
    agent = make_agent(library_database, ScriptedLLM(PLAN, SUFFICIENT, SYNTHESIS),
                       BrokenRepository(library_database))

    result = agent.research(OBJECTIVE)

    assert result.status is ResponseStatus.ANSWERED
    assert result.warnings[-1].startswith("The research could not be saved")
