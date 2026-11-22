"""Turns a research objective into a plan of commands (F03, SD01).

The model proposes the steps; the planner turns them into command objects.
If the model is missing, fails, or replies with nothing usable, a fixed
plan is used instead, so research can always start.
"""

from __future__ import annotations

from praxis.agent.prompts import PromptBuilder
from praxis.llm import LLMClient, LLMError, Prompt
from praxis.reader_model import ReaderProfile
from praxis.research.assessment import ResearchAssessment
from praxis.research.commands import (
    COMMAND_TYPES,
    ResearchCommand,
    RetrieveEvidenceCommand,
    RetrieveTheoryCommand,
)
from praxis.research.plan import ResearchPlan
from praxis.research.session import ResearchSession

FALLBACK_FOLLOW_UP_WARNING = (
    "The follow-up could not be planned, so it was searched as given."
)
FALLBACK_PLAN_WARNING = (
    "The research plan could not be generated, so a basic plan "
    "(search the question as asked) was used."
)


class ResearchPlanner:
    def __init__(self, llm: LLMClient | None, prompts: PromptBuilder | None = None) -> None:
        self._llm = llm
        self._prompts = prompts or PromptBuilder()

    def create_initial_plan(
        self, session: ResearchSession, profile: ReaderProfile | None = None
    ) -> ResearchPlan:
        """A plan for ``session.objective``.

        The objective as asked is always searched last, to top up whatever
        the model's keywords missed.
        """
        objective = session.objective
        commands = self._planned_commands(session, profile)
        if not commands:
            session.add_warning(FALLBACK_PLAN_WARNING)
            commands = [RetrieveTheoryCommand(objective)]
        commands.append(RetrieveEvidenceCommand(objective))
        return ResearchPlan(objective, commands)

    def plan_follow_up(
        self, session: ResearchSession, focus: str, profile: ReaderProfile | None = None
    ) -> list[ResearchCommand]:
        """Commands for continuing ``session`` in the direction ``focus``:
        the focus as the reader typed it first, then the model's steps.

        The reader's own words go first because a round's source limit can
        end it before every step runs."""
        commands = self._ask_for_plan(
            session, self._prompts.build_follow_up_plan_prompt(session.objective, focus, profile)
        )
        if not commands:
            session.add_warning(FALLBACK_FOLLOW_UP_WARNING)
        return [RetrieveEvidenceCommand(focus), *commands]

    def revise_plan(
        self, plan: ResearchPlan, assessment: ResearchAssessment
    ) -> list[ResearchCommand]:
        """Queue the assessment's follow-up searches and return the commands
        added. Searches already queued or run are not added again, so an
        empty list means the assessment found nothing new to do."""
        if not assessment.requires_more_research:
            return []
        added = []
        for follow_up in assessment.follow_ups:
            command = COMMAND_TYPES[follow_up.kind](follow_up.keywords)
            if plan.add_command(command):
                added.append(command)
        return added

    def revise_after_failure(
        self,
        plan: ResearchPlan,
        command: ResearchCommand,
        error: str | None,
        session: ResearchSession,
    ) -> ResearchCommand | None:
        """Schedule a retry of a failed command to run next, and return it;
        or, when it has no attempts left, record what could not be obtained
        and return None."""
        if command.can_retry:
            retry = command.retry()
            plan.add_first(retry)
            return retry
        session.add_warning(
            f"'{command.describe()}' failed ({error or 'unknown error'}); "
            "the material it was meant to find is missing from these results."
        )
        return None

    def _planned_commands(
        self, session: ResearchSession, profile: ReaderProfile | None
    ) -> list[ResearchCommand]:
        return self._ask_for_plan(session, self._prompts.build_plan_prompt(session.objective, profile))

    def _ask_for_plan(self, session: ResearchSession, prompt: Prompt) -> list[ResearchCommand]:
        """The model's plan as commands; empty if there is no model, it
        fails, or the reply has no usable step."""
        if self._llm is None:
            return []
        try:
            response = self._llm.generate(prompt)
        except LLMError:
            session.increment_llm_calls()
            return []
        session.increment_llm_calls(response.total_tokens)
        return [
            COMMAND_TYPES[kind](keywords)
            for kind, keywords in self._prompts.parse_plan(response.text)
        ]
