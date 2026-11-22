"""PoliticalResearchAgent.research (F03, SD01)."""

import subprocess
import sys

import pytest
from conftest import ScriptedLLM

from praxis.agent import AgentError, PoliticalResearchAgent, ResponseStatus
from praxis.agent.agent import NO_RESEARCH_SOURCES, NO_SYNTHESIS_BUDGET
from praxis.llm import LLMError
from praxis.persistence import SQLDocumentRepository, SQLReaderProfileRepository
from praxis.reader_model.service import ReaderProfileService
from praxis.research import ResearchBudget, ResearchStatus
from praxis.research.planner import FALLBACK_PLAN_WARNING
from praxis.research.policy import StopReason
from praxis.tools import PassageSearchTool, Tool, ToolManager, ToolResult

OBJECTIVE = "Why did the German revolution of 1848 fail?"
PLAN = "history: 1848 revolution Germany\ntheory: bourgeoisie state"
SYNTHESIS = (
    "## Findings\nThe bourgeoisie made peace with the monarchy [1].\n\n"
    "## Historical context\nWorkers fought on the barricades [2].\n\n"
    "## Theoretical connections\nThe state manages bourgeois affairs [3].\n\n"
    "## Open questions\n- What did the peasantry do?\n- Why was Prussia decisive?\n"
)
# An assessment that adds findings but asks for nothing more.
SUFFICIENT = "development: The bourgeoisie turned against the revolution [1]\nverdict: sufficient"


class FlakySearch(Tool):
    """Fails the first ``failures`` calls, then searches normally."""

    name = "passage_search"
    description = "flaky"

    def __init__(self, database, failures):
        self.inner = PassageSearchTool(SQLDocumentRepository(database))
        self.failures = failures

    def validate(self, tool_input):
        return self.inner.validate(tool_input)

    def execute(self, tool_input):
        if self.failures:
            self.failures -= 1
            return ToolResult.failure(self.name, "index unavailable")
        return self.inner.execute(tool_input)


def make_agent(database, llm, tool=None):
    tools = ToolManager()
    tools.register_tool(tool or PassageSearchTool(SQLDocumentRepository(database)))
    profiles = ReaderProfileService(SQLReaderProfileRepository(database))
    return PoliticalResearchAgent(tools, profiles, llm)


def test_research_plans_retrieves_and_synthesises(library_database):
    llm = ScriptedLLM(PLAN, SUFFICIENT, SYNTHESIS)

    result = make_agent(library_database, llm).research(OBJECTIVE)

    session = result.session
    assert result.status is ResponseStatus.ANSWERED and result.is_grounded
    assert session.status is ResearchStatus.COMPLETED
    assert result.stop_reason is StopReason.SUFFICIENT
    assert [step.description for step in session.steps] == [
        "Trace historical development: 1848 revolution Germany",
        "Retrieve theory: bourgeoisie state",
        f"Retrieve evidence: {OBJECTIVE}",
        "Assess the research so far: 1 historical development; research judged sufficient",
    ]
    assert all(step.succeeded for step in session.steps)
    assert result.purposes[1] == "history"
    assert "1848" in result.sources[0].citation.quoted_text
    assert result.summary.startswith("## Findings")
    assert "Open questions" not in result.summary
    assert result.open_questions == ("What did the peasantry do?", "Why was Prussia decisive?")
    assert [s.number for s in result.cited] == [1, 2, 3]
    assert result.warnings == ()
    assert not result.is_incomplete and result.unfinished_steps == []
    assert (session.llm_call_count, session.tokens_used) == (3, 45)
    assert session.tool_call_count == 3
    assert "### Retrieved for historical development" in llm.prompts[1].user
    assert result.situation.developments[0].evidence == (1,)
    assert "- development: The bourgeoisie turned against the revolution [1]" in llm.prompts[2].user


def test_no_sources_means_no_analysis(library_database):
    llm = ScriptedLLM("evidence: tariffs customs duties")

    result = make_agent(library_database, llm).research("What about tariffs?")

    assert result.status is ResponseStatus.NO_SOURCES
    assert result.session.status is ResearchStatus.FAILED
    assert result.summary is None and result.sources == ()
    assert result.warnings[-1] == NO_RESEARCH_SOURCES
    assert len(llm.prompts) == 1  # planning only; nothing was synthesised


def test_a_failed_step_is_retried_next_and_linked_to_the_failure(library_database):
    llm = ScriptedLLM(PLAN, SUFFICIENT, SYNTHESIS)
    agent = make_agent(library_database, llm, FlakySearch(library_database, failures=1))

    result = agent.research(OBJECTIVE)

    steps = result.session.steps
    assert not steps[0].succeeded and steps[0].error == "index unavailable"
    assert steps[1].succeeded and steps[1].retry_of == 0
    assert steps[1].description == steps[0].description
    assert result.status is ResponseStatus.ANSWERED
    assert result.warnings == ()


def test_a_step_that_keeps_failing_is_reported_missing(library_database):
    llm = ScriptedLLM(PLAN, SUFFICIENT, SYNTHESIS)
    # Both attempts of the first step fail; the rest succeed.
    agent = make_agent(library_database, llm, FlakySearch(library_database, failures=2))

    result = agent.research(OBJECTIVE)

    assert [s.succeeded for s in result.session.steps[:2]] == [False, False]
    assert "'Trace historical development: 1848 revolution Germany' failed" in result.warnings[0]
    assert result.status is ResponseStatus.ANSWERED


def test_budget_stops_research_early_and_says_what_was_skipped(library_database):
    llm = ScriptedLLM(PLAN, SYNTHESIS)

    result = make_agent(library_database, llm).research(
        OBJECTIVE, ResearchBudget(max_tool_calls=1)
    )

    assert result.stop_reason is StopReason.TOOL_CALLS
    assert len(result.session.steps) == 1
    assert result.warnings[0].startswith("Research stopped early because the tool-call limit")
    assert "Retrieve theory: bourgeoisie state" in result.warnings[0]
    assert "Research stopped before every planned step ran" in llm.prompts[1].user
    assert result.is_incomplete
    assert [c.describe() for c in result.unfinished_steps] == [
        "Retrieve theory: bourgeoisie state",
        f"Retrieve evidence: {OBJECTIVE}",
    ]
    assert [c.describe() for c in result.plan.taken] == [
        "Trace historical development: 1848 revolution Germany",
    ]


def test_without_a_model_the_sources_are_still_gathered(library_database):
    result = make_agent(library_database, None).research("bourgeoisie monarchy")

    assert result.status is ResponseStatus.EXPLANATION_FAILED
    assert result.sources
    assert result.session.status is ResearchStatus.COMPLETED
    assert FALLBACK_PLAN_WARNING in result.warnings
    assert "No language model is configured" in result.warnings[-1]


def test_synthesis_failure_keeps_the_sources(library_database):
    llm = ScriptedLLM(PLAN, SUFFICIENT, LLMError("rate limited"))

    result = make_agent(library_database, llm).research(OBJECTIVE)

    assert result.status is ResponseStatus.EXPLANATION_FAILED
    assert result.sources and result.summary is None
    assert result.warnings[-1] == "The analysis could not be generated: rate limited"
    assert result.session.llm_call_count == 3


def test_no_synthesis_when_the_model_budget_is_spent(library_database):
    llm = ScriptedLLM(PLAN)

    result = make_agent(library_database, llm).research(
        OBJECTIVE, ResearchBudget(max_llm_calls=1)
    )

    assert result.status is ResponseStatus.EXPLANATION_FAILED
    assert result.warnings[-1] == NO_SYNTHESIS_BUDGET
    assert len(llm.prompts) == 1


def test_citations_outside_the_sources_are_flagged(library_database):
    llm = ScriptedLLM(PLAN, SUFFICIENT, "## Findings\nThe revolution failed [1] [9].")

    result = make_agent(library_database, llm).research(OBJECTIVE)

    assert any("refers to [9]" in w for w in result.warnings)
    assert result.open_questions == ()


def test_an_empty_objective_is_rejected(library_database):
    with pytest.raises(AgentError):
        make_agent(library_database, None).research("   ")


@pytest.mark.parametrize("module", [
    "praxis.research.commands", "praxis.agent", "praxis.research.result",
    "praxis.persistence.research", "praxis.tools",
])
def test_packages_import_in_any_order(module):
    """praxis.agent and praxis.research depend on each other's modules; a
    fresh interpreter must be able to import either first."""
    completed = subprocess.run(
        [sys.executable, "-c", f"import {module}; from praxis.agent import PoliticalResearchAgent"],
        capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr


# --- assessment and plan revision (SD01 loop) ------------------------------------

MORE = (
    "contradiction: bourgeoisie | workers | the bourgeoisie feared the workers it needed [2]\n"
    "relation: class | Workers fought while the liberals held back [9]\n"
    "search: relation | wage labour subsistence\n"
    "question: Did the workers have their own organisations?\n"
    "verdict: more research needed"
)


def test_assessment_adds_searches_that_run_before_research_stops(library_database):
    llm = ScriptedLLM(PLAN, MORE, SUFFICIENT, SYNTHESIS)

    result = make_agent(library_database, llm).research(OBJECTIVE)

    steps = [step.description for step in result.session.steps]
    assert steps[3:] == [
        "Assess the research so far: 1 contradiction, 1 relation; 1 search added",
        "Investigate relation: wage labour subsistence",
        "Assess the research so far: 1 historical development; research judged sufficient",
    ]
    assert result.session.steps[3].is_assessment and result.session.iteration_count == 4
    assert result.stop_reason is StopReason.SUFFICIENT
    new = result.session.steps[4].new_sources
    assert new and all(result.purposes[n] == "relation" for n in new)
    situation = result.situation
    assert situation.contradictions[0].pole_b == "workers"
    assert situation.relations == []  # cited [9], which was never retrieved
    assert "1 finding from the assessment cited no retrieved passage and was left out." in result.warnings
    # The second assessment sees the first one's findings and searches.
    assert "Already established (do not repeat these):\n- contradiction: bourgeoisie | workers" in llm.prompts[2].user
    assert "- Investigate relation: wage labour subsistence" in llm.prompts[2].user
    synthesis = llm.prompts[3].user
    assert "Questions raised during the research:\n- Did the workers have their own organisations?" in synthesis
    assert "## Contradictions" in llm.prompts[3].system


def test_research_stops_when_the_assessment_only_repeats_searches(library_database):
    repeat = "search: history | 1848 revolution Germany\nverdict: more research needed"
    llm = ScriptedLLM(PLAN, repeat, SYNTHESIS)

    result = make_agent(library_database, llm).research(OBJECTIVE)

    assert result.stop_reason is StopReason.NO_USEFUL_STEPS
    assert result.session.steps[-1].description.endswith("; no new search to add")
    assert result.status is ResponseStatus.ANSWERED


def test_a_failed_assessment_still_lets_the_sources_be_synthesised(library_database):
    llm = ScriptedLLM(PLAN, LLMError("timeout"), SYNTHESIS)

    result = make_agent(library_database, llm).research(OBJECTIVE)

    last = result.session.steps[-1]
    assert last.is_assessment and not last.succeeded
    assert result.stop_reason is StopReason.PLAN_COMPLETE
    assert "The research could not be assessed (timeout)" in result.warnings[0]
    assert result.status is ResponseStatus.ANSWERED


def test_no_assessment_when_it_would_leave_no_call_for_the_synthesis(library_database):
    llm = ScriptedLLM(PLAN, SYNTHESIS)

    result = make_agent(library_database, llm).research(OBJECTIVE, ResearchBudget(max_llm_calls=2))

    assert not any(step.is_assessment for step in result.session.steps)
    assert result.stop_reason is StopReason.PLAN_COMPLETE
    assert result.status is ResponseStatus.ANSWERED
