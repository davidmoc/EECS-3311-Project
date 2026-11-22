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


def test_resume_starts_a_new_round_keeping_earlier_work():
    session = ResearchSession("wages", started_at=START)
    session.increment_iteration()
    session.increment_tool_calls()
    session.increment_llm_calls(tokens=40)
    session.record_step(StepRecord("Retrieve evidence: wages", True, (1,)))
    session.add_warning("Research stopped early.")
    session.complete(at=START + timedelta(seconds=30))
    later = START + timedelta(days=1)

    session.resume(at=later)
    session.increment_iteration()
    session.record_step(StepRecord("Retrieve theory: value", True, (2,)))

    assert session.status is ResearchStatus.RUNNING and session.finished_at is None
    assert session.rounds == 2
    assert [step.round for step in session.steps] == [1, 2]
    assert (session.iteration_count, session.round_iteration_count) == (2, 1)
    assert (session.tool_call_count, session.round_tool_call_count) == (1, 0)
    assert (session.llm_call_count, session.round_llm_call_count) == (1, 0)
    assert session.tokens_used == 40
    assert session.warnings == []
    assert session.round_elapsed_seconds(later + timedelta(seconds=5)) == 5
    assert session.elapsed_seconds(later) == 86400


def test_a_failed_session_can_be_resumed_but_a_running_one_cannot():
    failed = ResearchSession("wages")
    failed.fail("no sources")
    failed.resume()

    assert failed.is_running and failed.failure_reason is None
    with pytest.raises(ResearchError):
        failed.resume()
