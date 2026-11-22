"""Research commands and ResearchPlan (Command pattern, F03)."""

import pytest

from praxis.persistence import SQLDocumentRepository
from praxis.research import ResearchError, ResearchSession
from praxis.research.commands import (
    MAX_ATTEMPTS,
    InvestigateContradictionCommand,
    InvestigateRelationCommand,
    ResearchContext,
    RetrieveEvidenceCommand,
    RetrieveTheoryCommand,
    TraceHistoricalDevelopmentCommand,
)
from praxis.research.plan import ResearchPlan
from praxis.tools import PassageSearchTool, Tool, ToolManager, ToolResult


class BrokenSearch(Tool):
    name = "passage_search"
    description = "always fails"

    def validate(self, tool_input):
        return True

    def execute(self, tool_input):
        return ToolResult.failure(self.name, "index unavailable")


def make_context(library_database, tool=None, **kwargs):
    tools = ToolManager()
    tools.register_tool(tool or PassageSearchTool(SQLDocumentRepository(library_database)))
    return ResearchContext(ResearchSession("research"), tools, **kwargs)


def test_retrieval_adds_numbered_sources_and_records_their_purpose(library_database):
    context = make_context(library_database)

    outcome = TraceHistoricalDevelopmentCommand("1848 revolution bourgeoisie").execute(context)

    assert outcome.succeeded
    assert outcome.new_sources and outcome.new_sources[0] == 1
    assert "1848" in context.corpus.source(1).citation.quoted_text
    assert context.purposes == {n: "history" for n in outcome.new_sources}
    assert context.session.tool_call_count == 1


def test_sources_found_again_are_not_new(library_database):
    context = make_context(library_database)
    first = RetrieveEvidenceCommand("minimum wage").execute(context)

    again = RetrieveTheoryCommand("minimum wage").execute(context)

    assert first.new_sources == (1,)
    assert again.succeeded and again.new_sources == ()
    assert context.purposes == {1: "evidence"}  # first purpose is kept


def test_a_full_corpus_stops_retrieval_without_a_tool_call(library_database):
    context = make_context(library_database, max_sources=1)
    RetrieveEvidenceCommand("bourgeoisie").execute(context)

    outcome = RetrieveEvidenceCommand("class struggles").execute(context)

    assert len(context.corpus) == 1
    assert outcome.succeeded and outcome.new_sources == ()
    assert context.session.tool_call_count == 1


def test_tool_failure_is_an_outcome_not_an_exception(library_database):
    context = make_context(library_database, tool=BrokenSearch())

    outcome = RetrieveEvidenceCommand("wages").execute(context)

    assert not outcome.succeeded
    assert outcome.error == "index unavailable"
    assert context.corpus.is_empty


def test_retry_makes_the_next_attempt_until_attempts_run_out():
    command = RetrieveTheoryCommand("surplus value")

    retried = command.retry()

    assert retried == RetrieveTheoryCommand("surplus value", attempt=2)
    assert retried.attempt == MAX_ATTEMPTS and not retried.can_retry
    with pytest.raises(ResearchError):
        retried.retry()


def test_commands_describe_themselves():
    assert TraceHistoricalDevelopmentCommand("the 1848 revolutions").describe() == (
        "Trace historical development: the 1848 revolutions"
    )
    with pytest.raises(ResearchError):
        RetrieveEvidenceCommand("  ")


def test_plan_runs_commands_in_order_and_skips_duplicates():
    plan = ResearchPlan("wages", [
        RetrieveEvidenceCommand("wages"),
        RetrieveTheoryCommand("value"),
        RetrieveEvidenceCommand("wages"),
    ])

    assert len(plan) == 2
    assert plan.get_next_command() == RetrieveEvidenceCommand("wages")
    assert plan.get_next_command() == RetrieveTheoryCommand("value")
    assert plan.is_complete()
    with pytest.raises(ResearchError):
        plan.get_next_command()


def test_plan_puts_retries_first_and_can_be_replaced():
    plan = ResearchPlan("wages", [RetrieveEvidenceCommand("wages")])
    plan.add_first(RetrieveTheoryCommand("value", attempt=2))

    assert plan.pending[0] == RetrieveTheoryCommand("value", attempt=2)

    plan.replace_commands([TraceHistoricalDevelopmentCommand("enclosure")])
    assert plan.pending == [TraceHistoricalDevelopmentCommand("enclosure")]


def test_plan_never_queues_an_action_that_has_already_run():
    plan = ResearchPlan("wages", [RetrieveEvidenceCommand("wages")])
    plan.get_next_command()

    assert not plan.add_command(RetrieveEvidenceCommand("Wages"))  # same search, other case
    assert plan.add_command(RetrieveTheoryCommand("wages"))  # same words, other purpose
    assert plan.pending == [RetrieveTheoryCommand("wages")]


def test_investigation_commands_record_their_own_purpose(library_database):
    context = make_context(library_database)
    InvestigateRelationCommand("bourgeoisie").execute(context)
    InvestigateContradictionCommand("wage labour").execute(context)

    assert set(context.purposes.values()) == {"relation", "contradiction"}
    assert InvestigateRelationCommand("x").describe() == "Investigate relation: x"


def test_a_restored_plan_remembers_what_earlier_rounds_ran():
    earlier = [RetrieveEvidenceCommand("wages"), RetrieveTheoryCommand("value")]
    plan = ResearchPlan("wages", [RetrieveTheoryCommand("VALUE"), RetrieveEvidenceCommand("rent")],
                        taken=earlier)

    assert plan.pending == [RetrieveEvidenceCommand("rent")]
    assert plan.taken == earlier
    plan.get_next_command()
    assert plan.taken == [*earlier, RetrieveEvidenceCommand("rent")]
    assert not plan.add_command(RetrieveEvidenceCommand("Wages"))
