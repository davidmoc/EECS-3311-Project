"""ResearchSession and ResearchBudget (F03)."""

from datetime import datetime, timedelta, timezone

import pytest

from praxis.research import (
    ResearchBudget,
    ResearchError,
    ResearchSession,
    ResearchStatus,
    StepRecord,
)

START = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def test_session_starts_running_with_nothing_spent():
    session = ResearchSession("  Why  did the 1848 revolutions fail? ")

    assert session.objective == "Why did the 1848 revolutions fail?"
    assert session.status is ResearchStatus.RUNNING
    assert (session.iteration_count, session.tool_call_count, session.llm_call_count) == (0, 0, 0)
    assert session.steps == []


def test_session_requires_an_objective():
    with pytest.raises(ResearchError):
        ResearchSession("   ")


def test_counters_and_steps_accumulate():
    session = ResearchSession("wages")
    session.increment_iteration()
    session.increment_tool_calls()
    session.increment_tool_calls()
    session.increment_llm_calls(tokens=40)
    session.add_warning("planner fell back")
    session.add_warning("planner fell back")
    first = session.record_step(StepRecord("Retrieve evidence: wages", True, (1, 2)))
    second = session.record_step(StepRecord("Retry", False, error="down", retry_of=first))

    assert (session.iteration_count, session.tool_call_count, session.llm_call_count) == (1, 2, 1)
    assert session.tokens_used == 40
    assert session.warnings == ["planner fell back"]
    assert (first, second) == (0, 1)
    assert session.steps[1].retry_of == 0


def test_complete_and_fail_end_the_session():
    done = ResearchSession("wages", started_at=START)
    done.complete(at=START + timedelta(seconds=30))
    failed = ResearchSession("wages")
    failed.fail("no sources")

    assert done.status is ResearchStatus.COMPLETED
    assert done.elapsed_seconds(START + timedelta(hours=1)) == 30
    assert failed.status is ResearchStatus.FAILED
    assert failed.failure_reason == "no sources"


def test_a_finished_session_cannot_be_changed():
    session = ResearchSession("wages")
    session.complete()

    for change in (session.increment_iteration, session.increment_tool_calls, session.complete):
        with pytest.raises(ResearchError):
            change()
    with pytest.raises(ResearchError):
        session.fail("late")


def test_elapsed_time_runs_until_finished():
    session = ResearchSession("wages", started_at=START)

    assert session.elapsed_seconds(START + timedelta(seconds=12)) == 12


def test_budget_limits_must_be_positive():
    assert ResearchBudget().max_tool_calls > 0
    with pytest.raises(ResearchError):
        ResearchBudget(max_tool_calls=0)
    with pytest.raises(ResearchError):
        ResearchBudget(max_duration_seconds=-1)
