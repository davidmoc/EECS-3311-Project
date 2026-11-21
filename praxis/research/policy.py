"""Decides when the research loop should stop (F03, SD01)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import Enum

from praxis.research.commands import ResearchContext
from praxis.research.plan import ResearchPlan
from praxis.research.session import ResearchBudget, ResearchSession, utc_now

class StopReason(Enum):
    PLAN_COMPLETE = "every planned step has run"
    SOURCES_FULL = "enough sources were gathered"
    ITERATIONS = "the step limit was reached"
    TOOL_CALLS = "the tool-call limit was reached"
    DURATION = "the time limit was reached"

    @property
    def is_budget(self) -> bool:
        return self in _BUDGET_REASONS


_BUDGET_REASONS = {
    StopReason.ITERATIONS,
    StopReason.TOOL_CALLS,
    StopReason.DURATION,
}


class ResearchStoppingPolicy:
    def __init__(self, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock

    def should_stop(
        self,
        session: ResearchSession,
        budget: ResearchBudget,
        plan: ResearchPlan,
        context: ResearchContext,
    ) -> bool:
        return self.stop_reason(session, budget, plan, context) is not None

    def stop_reason(
        self,
        session: ResearchSession,
        budget: ResearchBudget,
        plan: ResearchPlan,
        context: ResearchContext,
    ) -> StopReason | None:
        """Why the loop should stop now, or None to run another step.

        The budget is checked first: when research both runs out of budget
        and of steps, the reader should hear about the budget.
        """
        exceeded = self.budget_exceeded(session, budget)
        if exceeded:
            return exceeded
        if context.corpus_full:
            return StopReason.SOURCES_FULL
        if plan.is_complete():
            return StopReason.PLAN_COMPLETE
        return None

    def budget_exceeded(
        self, session: ResearchSession, budget: ResearchBudget
    ) -> StopReason | None:
        """The limit that stops further retrieval steps, if any.

        Model calls are not checked here: retrieval steps do not use the
        model, so a spent model budget limits only the model's own work
        (the synthesis), never the gathering of sources.
        """
        if session.iteration_count >= budget.max_iterations:
            return StopReason.ITERATIONS
        if session.tool_call_count >= budget.max_tool_calls:
            return StopReason.TOOL_CALLS
        if session.elapsed_seconds(self._clock()) >= budget.max_duration_seconds:
            return StopReason.DURATION
        return None
