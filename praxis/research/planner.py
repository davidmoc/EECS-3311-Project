"""Turns a research objective into a plan of commands (F03, SD01).

The model proposes the steps; the planner turns them into command objects.
If the model is missing, fails, or replies with nothing usable, a fixed
plan is used instead, so research can always start.
"""

from __future__ import annotations

from praxis.agent.prompts import PromptBuilder
from praxis.llm import LLMClient, LLMError
from praxis.reader_model import ReaderProfile
from praxis.research.commands import (
    COMMAND_TYPES,
    ResearchCommand,
    RetrieveEvidenceCommand,
    RetrieveTheoryCommand,
)
from praxis.research.plan import ResearchPlan
from praxis.research.session import ResearchSession

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

    def _planned_commands(
        self, session: ResearchSession, profile: ReaderProfile | None
    ) -> list[ResearchCommand]:
        if self._llm is None:
            return []
        prompt = self._prompts.build_plan_prompt(session.objective, profile)
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
