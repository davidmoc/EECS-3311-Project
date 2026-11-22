"""ResearchStoppingPolicy (F03)."""

from datetime import datetime, timedelta, timezone

import pytest

from praxis.research import ResearchBudget, ResearchSession
from praxis.research.assessment import ResearchAssessment
from praxis.research.commands import ResearchContext, RetrieveEvidenceCommand
from praxis.research.plan import ResearchPlan
from praxis.research.policy import ResearchStoppingPolicy, StopReason
from praxis.tools import ToolManager

START = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
BUDGET = ResearchBudget(max_iterations=3, max_tool_calls=4, max_duration_seconds=60, max_llm_calls=3)


@pytest.fixture
def setup():
    session = ResearchSession("wages", started_at=START)
    context = ResearchContext(session, ToolManager())
    plan = ResearchPlan("wages", [RetrieveEvidenceCommand("wages")])
    return session, context, plan


def policy(seconds_later=0):
    return ResearchStoppingPolicy(clock=lambda: START + timedelta(seconds=seconds_later))


def test_continues_while_steps_remain_within_budget(setup):
    session, context, plan = setup

    assert policy().stop_reason(session, BUDGET, plan, context) is None
    assert not policy().should_stop(session, BUDGET, plan, context)


def test_stops_when_the_plan_is_done(setup):
    session, context, _ = setup

    reason = policy().stop_reason(session, BUDGET, ResearchPlan("wages"), context)

    assert reason is StopReason.PLAN_COMPLETE and not reason.is_budget


def test_stops_when_the_corpus_is_full(setup):
    session, _, plan = setup
    full = ResearchContext(session, ToolManager(), max_sources=0)

    assert policy().stop_reason(session, BUDGET, plan, full) is StopReason.SOURCES_FULL


@pytest.mark.parametrize(
    ("spend", "expected"),
    [
        (lambda s: [s.increment_iteration() for _ in range(3)], StopReason.ITERATIONS),
        (lambda s: [s.increment_tool_calls() for _ in range(4)], StopReason.TOOL_CALLS),
    ],
)
def test_stops_when_a_limit_is_reached(setup, spend, expected):
    session, context, plan = setup
    spend(session)

    reason = policy().stop_reason(session, BUDGET, plan, context)

    assert reason is expected and reason.is_budget


def test_a_spent_model_budget_does_not_stop_retrieval(setup):
    session, context, plan = setup
    for _ in range(3):
        session.increment_llm_calls()

    assert policy().stop_reason(session, BUDGET, plan, context) is None


def test_stops_when_time_runs_out(setup):
    session, context, plan = setup

    assert policy(59).stop_reason(session, BUDGET, plan, context) is None
    assert policy(60).stop_reason(session, BUDGET, plan, context) is StopReason.DURATION


def test_budget_is_reported_before_a_finished_plan(setup):
    session, context, _ = setup
    for _ in range(3):
        session.increment_iteration()

    assert policy().stop_reason(session, BUDGET, ResearchPlan("wages"), context) is StopReason.ITERATIONS


def test_stops_when_the_assessment_finds_the_research_sufficient(setup):
    session, context, plan = setup
    sufficient = ResearchAssessment(requires_more_research=False)

    reason = policy().stop_reason(session, BUDGET, plan, context, sufficient)

    assert reason is StopReason.SUFFICIENT and not reason.is_budget
    assert policy().should_stop(session, BUDGET, plan, context, sufficient)


def test_more_research_continues_only_if_the_revision_added_steps(setup):
    session, context, plan = setup
    more = ResearchAssessment(requires_more_research=True)

    assert policy().stop_reason(session, BUDGET, plan, context, more) is None
    assert policy().stop_reason(session, BUDGET, ResearchPlan("wages"), context, more) is StopReason.NO_USEFUL_STEPS


def test_budget_outranks_the_assessment(setup):
    session, context, plan = setup
    for _ in range(4):
        session.increment_tool_calls()

    reason = policy().stop_reason(session, BUDGET, plan, context, ResearchAssessment())

    assert reason is StopReason.TOOL_CALLS
