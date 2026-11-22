"""Facade over the agent subsystem.

Controllers call ``PoliticalResearchAgent`` and nothing else; retrieval,
prompt construction, the LLM and citation checking stay behind it.
"""

from __future__ import annotations

from praxis.agent.corpus import ResearchCorpus, Source, cited_numbers
from praxis.agent.prompts import PromptBuilder, reader_context
from praxis.agent.response import AgentResponse, ResponseStatus
from praxis.llm import LLMClient, LLMError
from praxis.reader_model.service import ReaderProfileService
from praxis.research.assessment import ResearchAssessment
from praxis.research.commands import ResearchCommand, ResearchContext
from praxis.research.method import DialecticalMaterialistResearchMethod, established_lines
from praxis.research.plan import ResearchPlan
from praxis.research.planner import ResearchPlanner
from praxis.research.policy import ResearchStoppingPolicy, StopReason
from praxis.research.result import ResearchResult
from praxis.research.session import ResearchBudget, ResearchSession, StepRecord
from praxis.research.situation import ConcreteSituation, ConcreteSituationBuilder
from praxis.tools import ToolManager

PASSAGES_PER_QUESTION = 6
PASSAGE_SEARCH = "passage_search"
ASSESS_STEP = "Assess the research so far"

NO_SOURCES_WARNING = (
    "No passage in the library addresses this question, so no answer was "
    "generated. Try other words, or import texts on this subject."
)
NO_LLM_WARNING = (
    "No language model is configured (set OPENAI_API_KEY), so only the "
    "passages are shown."
)
UNCITED_WARNING = (
    "The explanation does not cite any passage; treat it as unsupported "
    "commentary."
)
UNCITED_ANALYSIS_WARNING = (
    "The analysis does not cite any passage; treat it as unsupported "
    "commentary."
)
NO_RESEARCH_SOURCES = (
    "No passage in the library bears on this research question, so no "
    "analysis was written. Try other words, or import texts on this subject."
)
NO_SYNTHESIS_BUDGET = (
    "The model-call limit was used up before the findings could be written "
    "up, so only the sources are shown."
)


class AgentError(Exception):
    """The request itself was unusable (for example, an empty question)."""


class PoliticalResearchAgent:
    def __init__(
        self,
        tools: ToolManager,
        profiles: ReaderProfileService,
        llm: LLMClient | None = None,
        prompts: PromptBuilder | None = None,
        planner: ResearchPlanner | None = None,
        policy: ResearchStoppingPolicy | None = None,
        method: DialecticalMaterialistResearchMethod | None = None,
        builder: ConcreteSituationBuilder | None = None,
    ) -> None:
        """``llm`` may be None: the agent then still retrieves passages but
        cannot assess or explain them."""
        self._tools = tools
        self._profiles = profiles
        self._llm = llm
        self._prompts = prompts or PromptBuilder()
        self._planner = planner or ResearchPlanner(llm, self._prompts)
        self._policy = policy or ResearchStoppingPolicy()
        self._method = method or DialecticalMaterialistResearchMethod(llm, self._prompts)
        self._builder = builder or ConcreteSituationBuilder()

    # --- F03: multi-step research --------------------------------------------

    def research(self, objective: str, budget: ResearchBudget | None = None) -> ResearchResult:
        """Plan, retrieve step by step within ``budget``, then synthesise.

        Never fabricates: with no sources, no analysis is written; if the
        model is missing or fails, the gathered sources are still returned.
        """
        if not objective.strip():
            raise AgentError("Enter a research question first.")
        budget = budget or ResearchBudget()

        session = ResearchSession(objective)
        profile = self._profiles.get_profile()
        plan = self._planner.create_initial_plan(session, profile)
        context = ResearchContext(session, self._tools, profile=profile)
        situation = self._builder.build_initial_situation(session.objective)

        retried_from: dict[ResearchCommand, int] = {}  # retry -> failed step index
        assessment: ResearchAssessment | None = None  # of the sources so far
        while True:
            stop = self._policy.stop_reason(session, budget, plan, context, assessment)
            # When the plan runs out, assess what was found and let the
            # assessment revise the plan; the policy then decides again.
            if stop is StopReason.PLAN_COMPLETE and self._can_assess(session, budget, context):
                assessment = self._assess_and_revise(situation, context, plan)
                if assessment is not None:
                    continue
            if stop is not None:
                break

            assessment = None  # the next step's sources are not yet assessed
            command = plan.get_next_command()
            session.increment_iteration()
            outcome = command.execute(context)
            index = session.record_step(
                StepRecord(
                    command.describe(),
                    outcome.succeeded,
                    outcome.new_sources,
                    outcome.error,
                    retry_of=retried_from.pop(command, None),
                )
            )
            if outcome.succeeded:
                self._builder.update_situation(situation, outcome, context)
            else:
                retry = self._planner.revise_after_failure(plan, command, outcome.error, session)
                if retry is not None:
                    retried_from[retry] = index

        return self._finish_research(session, budget, plan, context, situation, stop)

    def _can_assess(
        self, session: ResearchSession, budget: ResearchBudget, context: ResearchContext
    ) -> bool:
        """An assessment needs sources and a model call, and must leave one
        model call for the synthesis."""
        return (
            self._method.available
            and not context.corpus.is_empty
            and session.round_llm_call_count + 1 < budget.max_llm_calls
        )

    def _assess_and_revise(
        self, situation: ConcreteSituation, context: ResearchContext, plan: ResearchPlan
    ) -> ResearchAssessment | None:
        """SD01's assess → updateSituation → revisePlan, recorded as a step."""
        session = context.session
        assessment = self._method.assess(situation, context)
        if assessment is None:
            session.record_step(
                StepRecord(ASSESS_STEP, False, error="no usable assessment", is_assessment=True)
            )
            return None

        rejected = self._builder.integrate_assessment(situation, assessment)
        if rejected:
            session.add_warning(
                f"{rejected} finding{'s' if rejected != 1 else ''} from the assessment "
                "cited no retrieved passage and "
                f"{'were' if rejected != 1 else 'was'} left out."
            )
        added = self._planner.revise_plan(plan, assessment)
        if not assessment.requires_more_research:
            outcome = "research judged sufficient"
        elif added:
            outcome = f"{len(added)} search{'es' if len(added) != 1 else ''} added"
        else:
            outcome = "no new search to add"
        session.record_step(
            StepRecord(f"{ASSESS_STEP}: {assessment.summary()}; {outcome}", True, is_assessment=True)
        )
        return assessment

    def _finish_research(
        self,
        session: ResearchSession,
        budget: ResearchBudget,
        plan: ResearchPlan,
        context: ResearchContext,
        situation: ConcreteSituation,
        stop: StopReason,
    ) -> ResearchResult:
        corpus = context.corpus
        skipped = plan.pending
        if corpus.is_empty:
            session.add_warning(NO_RESEARCH_SOURCES)
            session.fail("no sources found")
            return ResearchResult(
                session, ResponseStatus.NO_SOURCES, stop, situation=situation, plan=plan
            )

        unfinished = None
        if stop.is_budget and skipped:
            unfinished = stop.value
            steps = "; ".join(command.describe() for command in skipped)
            session.add_warning(f"Research stopped early because {stop.value}. Not run: {steps}.")

        def partial(warning: str) -> ResearchResult:
            session.add_warning(warning)
            session.complete()
            return ResearchResult(
                session, ResponseStatus.EXPLANATION_FAILED, stop,
                tuple(corpus.sources), dict(context.purposes), situation=situation, plan=plan,
            )

        if self._llm is None:
            return partial(NO_LLM_WARNING)
        if session.round_llm_call_count >= budget.max_llm_calls:
            return partial(NO_SYNTHESIS_BUDGET)

        prompt = self._prompts.build_research_prompt(
            session.objective, corpus, context.purposes, context.profile, unfinished,
            established=established_lines(situation),
            questions=situation.unresolved_questions,
        )
        try:
            response = self._llm.generate(prompt)
        except LLMError as exc:
            session.increment_llm_calls()
            return partial(f"The analysis could not be generated: {exc}")
        session.increment_llm_calls(response.total_tokens)

        cited, unknown = check_citations(response.text, corpus)
        if unknown:
            labels = ", ".join(f"[{n}]" for n in unknown)
            session.add_warning(
                f"The analysis refers to {labels}, which "
                f"{'is' if len(unknown) == 1 else 'are'} not among the sources; "
                "treat those statements as unsupported."
            )
        if not cited:
            session.add_warning(UNCITED_ANALYSIS_WARNING)
        summary, questions = self._prompts.split_open_questions(response.text)
        session.complete()
        return ResearchResult(
            session,
            ResponseStatus.ANSWERED,
            stop,
            tuple(corpus.sources),
            dict(context.purposes),
            summary=summary,
            cited=tuple(cited),
            open_questions=tuple(questions),
            personalized=reader_context(context.profile) is not None,
            situation=situation,
            plan=plan,
        )

    # --- F04: source-first question answering ------------------------------

    def answer_question(self, question: str) -> AgentResponse:
        question = question.strip()
        if not question:
            raise AgentError("Ask a question first.")

        profile = self._profiles.get_profile()
        usage = _Usage()
        warnings: list[str] = []

        terms = self._search_terms(question, usage)
        corpus = self._retrieve(question, terms, warnings)
        if corpus.is_empty:
            return AgentResponse(
                question,
                ResponseStatus.NO_SOURCES,
                warnings=(*warnings, NO_SOURCES_WARNING),
                tokens_used=usage.tokens,
                search_terms=tuple(terms),
            )

        sources = tuple(corpus.sources)
        if self._llm is None:
            return AgentResponse(
                question,
                ResponseStatus.EXPLANATION_FAILED,
                sources,
                warnings=(*warnings, NO_LLM_WARNING),
                search_terms=tuple(terms),
            )

        prompt = self._prompts.build_question_prompt(question, corpus, profile)
        try:
            response = self._llm.generate(prompt)
        except LLMError as exc:
            # The passages are the primary answer, so they are still returned.
            return AgentResponse(
                question,
                ResponseStatus.EXPLANATION_FAILED,
                sources,
                warnings=(*warnings, f"The explanation could not be generated: {exc}"),
                tokens_used=usage.tokens,
                search_terms=tuple(terms),
            )
        usage.tokens += response.total_tokens

        cited, unknown = check_citations(response.text, corpus)
        if unknown:
            labels = ", ".join(f"[{n}]" for n in unknown)
            warnings.append(
                f"The explanation refers to {labels}, which "
                f"{'is' if len(unknown) == 1 else 'are'} not among the sources; "
                "treat those statements as unsupported."
            )
        if not cited:
            warnings.append(UNCITED_WARNING)

        return AgentResponse(
            question,
            ResponseStatus.ANSWERED,
            sources,
            explanation=response.text,
            cited=tuple(cited),
            warnings=tuple(warnings),
            personalized=reader_context(profile) is not None,
            tokens_used=usage.tokens,
            search_terms=tuple(terms),
        )

    # --- steps ---------------------------------------------------------------

    def _search_terms(self, question: str, usage: _Usage) -> list[str]:
        """Keywords chosen by the model, or none if it cannot help.

        The question is always searched as well, so a failure here only
        makes retrieval less focused; it never stops the answer.
        """
        if self._llm is None:
            return []
        try:
            response = self._llm.generate(self._prompts.build_search_terms_prompt(question))
        except LLMError:
            return []
        usage.tokens += response.total_tokens
        return self._prompts.parse_search_terms(response.text)

    def _retrieve(
        self, question: str, terms: list[str], warnings: list[str]
    ) -> ResearchCorpus:
        """Passages for the model's keywords first, then for the question
        as asked, until ``PASSAGES_PER_QUESTION`` distinct passages."""
        queries = ([" ".join(terms)] if terms else []) + [question]
        corpus = ResearchCorpus()
        for query in queries:
            if len(corpus) >= PASSAGES_PER_QUESTION:
                break  # already full: another search would be thrown away
            result = self._tools.execute_tool(
                PASSAGE_SEARCH, {"query": query, "limit": PASSAGES_PER_QUESTION}
            )
            if not result.success:
                warnings.append(f"Library search failed: {result.error}")
                continue
            for match in result.items:
                if len(corpus) >= PASSAGES_PER_QUESTION:
                    return corpus
                corpus.add_passage(match.document, match.passage)
        return corpus


def check_citations(text: str, corpus: ResearchCorpus) -> tuple[list[Source], list[int]]:
    """The sources ``text`` cites, in order of first mention, and any cited
    numbers that are not in ``corpus``."""
    numbers = cited_numbers(text)
    cited = [corpus.source(n) for n in numbers if corpus.has_source(n)]
    unknown = [n for n in numbers if not corpus.has_source(n)]
    return cited, unknown


class _Usage:
    """Tokens spent on one request, across all of its model calls."""

    def __init__(self) -> None:
        self.tokens = 0
