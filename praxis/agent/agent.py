"""Facade over the agent subsystem.

Controllers call ``PoliticalResearchAgent`` and nothing else; retrieval,
prompt construction, the LLM and citation checking stay behind it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from praxis.agent.corpus import ResearchCorpus, Source, cited_numbers
from praxis.agent.prompts import PromptBuilder, reader_context
from praxis.agent.response import AgentResponse, ResponseStatus
from praxis.comparison import (
    Comparability,
    SourceComparison,
    SourceProfile,
    SourceSelection,
    check_points,
    parse_comparison,
)
from praxis.comparison.command import CompareSourcesCommand
from praxis.documents import Document, NewsArticle
from praxis.news.events import Event
from praxis.news.exploration import report_passage
from praxis.llm import LLMClient, LLMError
from praxis.reader_model.personalization import PersonalizationService, RequestPreferences
from praxis.reader_model.service import ReaderProfileService
from praxis.research.assessment import ResearchAssessment
from praxis.research.analysis import (
    THEORY_PURPOSE,
    AnalysisStatus,
    Concept,
    MaterialistAnalysis,
    check_analysis,
    parse_analysis,
    parse_concepts,
)
from praxis.research.commands import (
    PASSAGES_PER_STEP,
    ResearchCommand,
    ResearchContext,
    RetrieveEvidenceCommand,
    RetrieveTheoryCommand,
    TraceHistoricalDevelopmentCommand,
)
from praxis.research.history import (
    ContextStatus,
    HistoricalContext,
    HistoryPlan,
    check_items,
    parse_history,
    parse_history_plan,
    suggested_readings,
)
from praxis.research.method import DialecticalMaterialistResearchMethod, established_lines
from praxis.research.plan import ResearchPlan
from praxis.research.planner import ResearchPlanner
from praxis.research.policy import ResearchStoppingPolicy, StopReason
from praxis.research.result import ResearchResult
from praxis.research.session import ResearchBudget, ResearchSession, StepRecord
from praxis.research.situation import ConcreteSituation, ConcreteSituationBuilder
from praxis.tools import ToolManager

if TYPE_CHECKING:  # only for type hints: praxis.tools imports praxis.persistence
    from praxis.persistence.comparisons import ComparisonRepository, ComparisonSummary
    from praxis.persistence.research import ResearchRepository, ResearchSessionSummary

PASSAGES_PER_QUESTION = 6
# How many more sources one continuation of a research session may add.
SOURCES_PER_CONTINUATION = 10
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
NOTHING_TO_CONTINUE = (
    "This research has no unfinished steps or open questions to follow up. "
    "Give a direction to continue in."
)
NOT_SAVED_WARNING = "The research could not be saved, so it cannot be continued later: {}"
NO_SYNTHESIS_BUDGET = (
    "The model-call limit was used up before the findings could be written "
    "up, so only the sources are shown."
)

# Research on a news event starts from at most this many of its reports.
MAX_EVENT_REPORTS = 6
EVENT_PURPOSE = "event"
EVENT_QUESTION = "{headline}: what happened, why, and which classes and interests are involved?"

MAX_COMPARED_SOURCES = 4
# What a comparison is "on" when the reader named paragraphs but no subject.
SELECTED_PASSAGES = "the selected passages"
TOO_FEW_TO_COMPARE = (
    "Fewer than two of the chosen sources had passages to compare, so no "
    "comparison was made."
)
COMPARISON_UNREADABLE = (
    "The comparison could not be read, so only the passages are shown; "
    "compare them directly."
)
COMPARISON_NOT_STORED = "The comparison could not be stored, so it cannot be reopened: {}"
LOW_COMPARABILITY = (
    "These sources are not sufficiently comparable{reason} A direct "
    "comparison could mislead."
)


# Historical context (F09).
HISTORY_SOURCES = 15
EVENT_HISTORY_TOPIC = "the historical background of: {headline}"
HISTORY_PLAN_UNUSABLE = (
    "The model's search plan could not be used, so only the topic as typed "
    "was searched."
)
NO_HISTORY_SOURCES = (
    "No passage in the library bears on the history of this topic, so no "
    "account was written. Try other words, or import texts on it."
)
HISTORY_UNREADABLE = "The model's account could not be read, so only the passages are shown."
UNCITED_HISTORY = (
    "The account cites no retrieved passage, so it is not shown; read the "
    "passages directly."
)


# Marxist theoretical analysis (F11).
MAX_ANALYSIS_CONCEPTS = 4
NO_ANALYSIS_SOURCES = (
    "No passage in the library bears on this issue, so no analysis was "
    "written. Try other words, or import texts on it."
)
CONCEPTS_UNUSABLE = (
    "The model did not name usable concepts, so theory was searched for "
    "the {what} as typed."
)
NO_THEORY_FOUND = (
    "No theoretical passage in the library was found for these concepts, "
    "so no analysis was written; the evidence is shown."
)
ANALYSIS_UNREADABLE = "The model's analysis could not be read, so only the passages are shown."
UNCITED_ANALYSIS = (
    "The analysis cites no retrieved passage, so it is not shown; read the "
    "passages directly."
)
TENTATIVE_ANALYSIS = (
    "No claim in this analysis is borne out by several evidence passages, "
    "so treat it as tentative."
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
        research_repository: ResearchRepository | None = None,
        comparison_repository: ComparisonRepository | None = None,
    ) -> None:
        """``llm`` may be None: the agent then still retrieves passages but
        cannot assess or explain them. Without ``research_repository``,
        research results are not stored and cannot be continued; without
        ``comparison_repository``, comparisons are not stored."""
        self._tools = tools
        self._profiles = profiles
        self._personalization = PersonalizationService(profiles)
        self._llm = llm
        self._prompts = prompts or PromptBuilder()
        self._planner = planner or ResearchPlanner(llm, self._prompts)
        self._policy = policy or ResearchStoppingPolicy()
        self._method = method or DialecticalMaterialistResearchMethod(llm, self._prompts)
        self._builder = builder or ConcreteSituationBuilder()
        self._repository = research_repository
        self._comparisons = comparison_repository

    # --- F03: multi-step research --------------------------------------------

    def research(
        self,
        objective: str,
        budget: ResearchBudget | None = None,
        reports: tuple[NewsArticle, ...] = (),
        preferences: RequestPreferences | None = None,
    ) -> ResearchResult:
        """Plan, retrieve step by step within ``budget``, then synthesise.

        ``reports`` are news reports the research starts from: they become
        the first sources, before anything is searched (SD03's
        ``research(event)``). ``preferences`` override the reader's
        explanation depth or personalization for this request (F14).

        Never fabricates: with no sources, no analysis is written; if the
        model is missing or fails, the gathered sources are still returned.
        """
        if not objective.strip():
            raise AgentError("Enter a research question first.")
        session = ResearchSession(objective)
        profile = self._personalization.profile_for(preferences)
        plan = self._planner.create_initial_plan(session, profile)
        context = ResearchContext(session, self._tools, profile=profile)
        if reports:
            numbers = []
            for report in reports[:MAX_EVENT_REPORTS]:
                source = context.corpus.add_passage(report, report_passage(report))
                context.purposes[source.number] = EVENT_PURPOSE
                numbers.append(source.number)
            session.record_step(StepRecord(
                f"Start from the event's {len(numbers)} news report{'s' if len(numbers) != 1 else ''}",
                True, tuple(numbers),
            ))
        situation = self._builder.build_initial_situation(session.objective)
        return self._run(session, plan, context, situation, budget or ResearchBudget())

    def research_event(self, event: Event, budget: ResearchBudget | None = None) -> ResearchResult:
        """SD03's ``researchEvent``: a research session on a news event,
        starting from its reports."""
        return self.research(EVENT_QUESTION.format(headline=event.headline), budget, event.reports)

    def continue_research(
        self,
        session_id: UUID,
        focus: str | None = None,
        budget: ResearchBudget | None = None,
        preferences: RequestPreferences | None = None,
    ) -> ResearchResult:
        """Run another round of a stored research session (Stage 1's
        ``continueResearch(sessionId, request)``).

        The earlier sources keep their numbers and the earlier findings are
        kept. The round runs ``focus`` (if given: the focus as typed, then
        the model's plan for it) first, then any steps a
        limit left unrun, then assesses as usual; ``budget`` applies to this
        round only. The analysis is rewritten over all the sources.
        """
        previous = self.get_research(session_id)
        focus = " ".join((focus or "").split()) or None
        situation = previous.situation or self._builder.build_initial_situation(previous.objective)
        unfinished = previous.unfinished_steps
        if focus is None and not unfinished and not situation.unresolved_questions:
            raise AgentError(NOTHING_TO_CONTINUE)

        session = previous.session
        session.resume()
        profile = self._personalization.profile_for(preferences)
        context = ResearchContext(
            session, self._tools, _restore_corpus(previous), profile,
            max_sources=len(previous.sources) + SOURCES_PER_CONTINUATION,
            purposes=dict(previous.purposes),
        )
        commands = []
        if focus is not None:
            session.add_focus(focus)
            commands = self._planner.plan_follow_up(session, focus, profile)
        # Not `if previous.plan`: a plan with nothing queued has length 0, so is falsy.
        taken = previous.plan.taken if previous.plan is not None else []
        plan = ResearchPlan(session.objective, [*commands, *unfinished], taken=taken)
        return self._run(session, plan, context, situation, budget or ResearchBudget())

    def get_research(self, session_id: UUID) -> ResearchResult:
        """A stored research result, as it was last saved."""
        result = self._require_repository().get(session_id)
        if result is None:
            raise AgentError(f"There is no research session {session_id}.")
        return result

    def list_research(self, limit: int = 20) -> list[ResearchSessionSummary]:
        """Stored research sessions, most recently updated first."""
        return self._require_repository().list_recent(limit)

    def find_research(self, id_prefix: str) -> UUID:
        """The stored session whose id starts with ``id_prefix``."""
        prefix = id_prefix.strip().lower()
        if not prefix:
            raise AgentError("A research session id is required.")
        matches = self._require_repository().find_ids(prefix)
        if not matches:
            raise AgentError(f"No research session with id starting '{prefix}'.")
        if len(matches) > 1:
            raise AgentError(f"Id '{prefix}' matches {len(matches)} sessions; use more characters.")
        return matches[0]

    def _require_repository(self) -> ResearchRepository:
        if self._repository is None:
            raise AgentError("Research sessions are not being stored.")
        return self._repository

    def _run(
        self,
        session: ResearchSession,
        plan: ResearchPlan,
        context: ResearchContext,
        situation: ConcreteSituation,
        budget: ResearchBudget,
    ) -> ResearchResult:
        """SD01's loop: run commands, assess when the plan runs out, revise,
        until the policy stops it; then synthesise and store the result."""
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

        result = self._finish_research(session, budget, plan, context, situation, stop)
        self._store(result)
        return result

    def _store(self, result: ResearchResult) -> None:
        """Save ``result`` so it can be reopened and continued. A failure
        to save does not lose the result the reader is about to see."""
        if self._repository is None:
            return
        try:
            self._repository.save(result)
        except sqlite3.Error as exc:
            result.session.add_warning(NOT_SAVED_WARNING.format(exc))

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
            session.question, corpus, context.purposes, context.profile, unfinished,
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

    # --- F09: historical context ----------------------------------------------

    def explore_history(
        self,
        topic: str,
        allow_broad: bool = False,
        reports: tuple[NewsArticle, ...] = (),
        preferences: RequestPreferences | None = None,
    ) -> HistoricalContext:
        """How ``topic`` developed, organised from library passages (UC09).

        The model plans searches from the topic's origins onward and may
        judge the topic too broad; unless ``allow_broad``, nothing is then
        searched and narrower topics are suggested. ``reports`` (news) are
        the first sources: the present situation whose background is
        traced. Without a model, or if the account fails, the passages
        are still returned.
        """
        topic = " ".join(topic.split())
        if not topic:
            raise AgentError("Name a topic, event or period to trace.")
        profile = self._personalization.profile_for(preferences)
        usage = _Usage()
        warnings: list[str] = []

        searches: list[tuple[str, str]] = []
        if self._llm is not None:
            plan = self._history_plan(topic, usage)
            if plan is None:
                warnings.append(HISTORY_PLAN_UNUSABLE)
            elif plan.too_broad and not allow_broad:
                return HistoricalContext(
                    topic, ContextStatus.TOO_BROAD, narrower=plan.narrower,
                    tokens_used=usage.tokens,
                )
            else:
                searches = list(plan.searches)
        searches.append(("the topic as asked", topic))

        session = ResearchSession(topic)
        context = ResearchContext(
            session, self._tools, profile=profile, max_sources=HISTORY_SOURCES, library_only=True
        )
        steps = []
        if reports:
            for report in reports[:MAX_EVENT_REPORTS]:
                source = context.corpus.add_passage(report, report_passage(report))
                context.purposes[source.number] = EVENT_PURPOSE
            steps.append(f"Start from the event's news reports  {_added(len(context.corpus))}")
        done: set[tuple[type, str]] = set()
        for label, keywords in searches:
            command = TraceHistoricalDevelopmentCommand(keywords)
            if command.key in done:
                continue
            done.add(command.key)
            outcome = command.execute(context)
            if outcome.succeeded:
                steps.append(f"{label}: {keywords}  {_added(len(outcome.new_sources))}")
            else:
                steps.append(f"{label}: {keywords}  — failed: {outcome.error}")
                warnings.append(f"A library search failed: {outcome.error}")

        purposes = dict(context.purposes)
        sources = tuple(context.corpus.sources)

        def result(status: ContextStatus, note: str | None = None, **fields) -> HistoricalContext:
            return HistoricalContext(
                topic, status, sources=sources, purposes=purposes, steps=tuple(steps),
                warnings=tuple(warnings + ([note] if note else [])),
                tokens_used=usage.tokens, **fields,
            )

        if not any(purposes.get(s.number) != EVENT_PURPOSE for s in sources):
            return result(ContextStatus.NO_SOURCES, NO_HISTORY_SOURCES)
        if self._llm is None:
            return result(ContextStatus.NOT_ORGANISED, NO_LLM_WARNING)

        prompt = self._prompts.build_history_prompt(topic, context.corpus, purposes, profile)
        try:
            response = self._llm.generate(prompt)
        except LLMError as exc:
            return result(ContextStatus.NOT_ORGANISED, f"The account could not be generated: {exc}")
        usage.tokens += response.total_tokens

        parsed = parse_history(response.text)
        if parsed is None:
            return result(ContextStatus.NOT_ORGANISED, HISTORY_UNREADABLE)
        known = {source.number for source in sources}
        items, dropped = check_items(parsed.items, known)
        if dropped:
            warnings.append(
                f"{dropped} item{'s' if dropped != 1 else ''} of the account cited no retrieved "
                f"passage and {'were' if dropped != 1 else 'was'} left out."
            )
        overview_evidence = tuple(n for n in parsed.overview_evidence if n in known)
        overview = parsed.overview if overview_evidence else ""
        if parsed.overview and not overview_evidence:
            warnings.append("The overview cited no retrieved passage and was left out.")
        if not items and not overview:
            return result(ContextStatus.NOT_ORGANISED, UNCITED_HISTORY)

        cited = set(overview_evidence).union(*(item.evidence for item in items))
        readings = suggested_readings(tuple(
            s for s in sources if s.number in cited and purposes.get(s.number) != EVENT_PURPOSE
        ))
        return result(
            ContextStatus.EXPLAINED,
            overview=overview,
            overview_evidence=overview_evidence,
            items=tuple(items),
            gaps=parsed.gaps,
            readings=readings,
            personalized=reader_context(profile) is not None,
        )

    def explore_event_history(self, event: Event) -> HistoricalContext:
        """F09 from a news event: the background of what its reports
        describe, with the reports as the first sources."""
        return self.explore_history(
            EVENT_HISTORY_TOPIC.format(headline=event.headline), allow_broad=True, reports=event.reports
        )

    def _history_plan(self, topic: str, usage: _Usage) -> HistoryPlan | None:
        try:
            response = self._llm.generate(self._prompts.build_history_plan_prompt(topic))
        except LLMError:
            return None
        usage.tokens += response.total_tokens
        return parse_history_plan(response.text)

    # --- F11: Marxist theoretical analysis -----------------------------------

    def analyze(
        self,
        issue: str,
        framework: str | None = None,
        preferences: RequestPreferences | None = None,
    ) -> MaterialistAnalysis:
        """A Marxist analysis of ``issue`` from library passages (UC11).

        Evidence is searched for first; the model then names the concepts
        the evidence gives reason to apply (``framework`` first, if the
        reader asked for one), theory is retrieved for each, and the model
        connects the two. Without a model, the evidence is still returned.
        """
        issue = " ".join(issue.split())
        if not issue:
            raise AgentError("Name an issue, event or question to analyse.")
        profile = self._personalization.profile_for(preferences)
        usage = _Usage()
        context = ResearchContext(
            ResearchSession(issue), self._tools, profile=profile, library_only=True
        )
        terms = self._search_terms(issue, usage)
        for query in ([" ".join(terms)] if terms else []) + [issue]:
            RetrieveEvidenceCommand(query).execute(context)
        return self._analyse(issue, framework, context, usage)

    def analyze_research(
        self,
        session_id: UUID,
        framework: str | None = None,
        preferences: RequestPreferences | None = None,
    ) -> MaterialistAnalysis:
        """UC11 "reached as part of a broader research session": the
        session's sources are the evidence, and its findings are offered to
        the model; only theory is searched for."""
        research = self.get_research(session_id)
        corpus = _restore_corpus(research)
        context = ResearchContext(
            ResearchSession(research.objective), self._tools, corpus,
            self._personalization.profile_for(preferences),
            max_sources=len(corpus) + MAX_ANALYSIS_CONCEPTS * PASSAGES_PER_STEP,
            purposes=dict(research.purposes), library_only=True,
        )
        established = established_lines(research.situation) if research.situation else []
        return self._analyse(
            research.objective, framework, context, _Usage(), established,
            research_session=str(research.session.id)[:8],
        )

    def _analyse(
        self,
        issue: str,
        framework: str | None,
        context: ResearchContext,
        usage: _Usage,
        established: list[str] | None = None,
        research_session: str | None = None,
    ) -> MaterialistAnalysis:
        framework = " ".join((framework or "").split()) or None
        warnings: list[str] = []
        evidence = [s for s in context.corpus.sources if context.purposes.get(s.number) != THEORY_PURPOSE]
        concepts: list[Concept] = []

        def result(status: AnalysisStatus, note: str | None = None, **fields) -> MaterialistAnalysis:
            return MaterialistAnalysis(
                issue, status, framework, tuple(concepts),
                sources=tuple(context.corpus.sources), purposes=dict(context.purposes),
                research_session=research_session,
                warnings=tuple(warnings + ([note] if note else [])),
                tokens_used=usage.tokens, **fields,
            )

        if not evidence:
            return result(AnalysisStatus.NO_SOURCES, NO_ANALYSIS_SOURCES)
        if self._llm is None:
            return result(AnalysisStatus.NOT_ANALYSED, NO_LLM_WARNING)

        try:
            response = self._llm.generate(self._prompts.build_concept_prompt(issue, evidence, framework))
            usage.tokens += response.total_tokens
            concepts = parse_concepts(response.text)
        except LLMError:
            concepts = []
        if not concepts:
            what = "framework" if framework else "issue"
            warnings.append(CONCEPTS_UNUSABLE.format(what=what))
            concepts = [Concept(framework or issue)]

        theory_found = False
        for concept in concepts[:MAX_ANALYSIS_CONCEPTS]:
            outcome = RetrieveTheoryCommand(f"{concept.name} {concept.keywords}").execute(context)
            if not outcome.succeeded:
                warnings.append(f"The theory search for {concept.name} failed: {outcome.error}")
            theory_found = theory_found or bool(outcome.new_sources)
        theory_found = theory_found or any(
            context.purposes.get(s.number) == THEORY_PURPOSE for s in context.corpus.sources
        )
        if not theory_found:
            return result(AnalysisStatus.NO_THEORY, NO_THEORY_FOUND)

        profile = context.profile
        prompt = self._prompts.build_analysis_prompt(
            issue, context.corpus, context.purposes, framework, established or [], profile
        )
        try:
            response = self._llm.generate(prompt)
        except LLMError as exc:
            return result(AnalysisStatus.NOT_ANALYSED, f"The analysis could not be generated: {exc}")
        usage.tokens += response.total_tokens

        parsed = parse_analysis(response.text)
        if parsed is None:
            return result(AnalysisStatus.NOT_ANALYSED, ANALYSIS_UNREADABLE)
        known = {source.number for source in context.corpus.sources}
        items, dropped = check_analysis(parsed.items, context.purposes, known)
        if dropped:
            warnings.append(
                f"{dropped} part{'s' if dropped != 1 else ''} of the analysis did not cite the "
                f"passages {'they' if dropped != 1 else 'it'} needed "
                f"(an application needs theory and evidence) and {'were' if dropped != 1 else 'was'} left out."
            )
        if not items:
            return result(AnalysisStatus.NOT_ANALYSED, UNCITED_ANALYSIS)

        cited = {n for item in items for n in item.evidence}
        readings = suggested_readings(tuple(
            s for s in context.corpus.sources
            if s.number in cited and context.purposes.get(s.number) == THEORY_PURPOSE
        ))
        analysis = result(
            AnalysisStatus.ANALYSED,
            items=tuple(items),
            limits=parsed.limits,
            readings=readings,
            personalized=reader_context(profile) is not None,
        )
        if analysis.is_tentative:
            analysis = replace(analysis, warnings=(TENTATIVE_ANALYSIS, *analysis.warnings))
        return analysis

    # --- F10: source and framing comparison --------------------------------

    def compare_sources(
        self, selections: list[SourceSelection], subject: str = ""
    ) -> SourceComparison:
        """Compare how the chosen sources treat ``subject`` (SD06).

        Each source is retrieved through the tool layer, then the model
        compares the passages. The passages are always returned; without
        a model, or if it fails, they are all the reader gets. A
        comparison of two or more sources is stored.
        """
        comparison = self._compare(selections, subject)
        if self._comparisons is not None and len(comparison.profiles) >= 2:
            try:
                self._comparisons.save(comparison)
            except sqlite3.Error as exc:
                comparison.warnings = (*comparison.warnings, COMPARISON_NOT_STORED.format(exc))
        return comparison

    def compare_research_sources(self, session_id: UUID) -> SourceComparison:
        """Compare the texts a stored research session drew on, on its
        question, using the passages the research retrieved from each
        (UC10: "requests a comparison from an event or research view")."""
        research = self.get_research(session_id)
        by_document: dict[UUID, list[Source]] = {}
        for source in research.sources:
            by_document.setdefault(source.citation.document_id, []).append(source)
        if len(by_document) < 2:
            raise AgentError("This research drew on only one text, so there is nothing to compare.")
        # The texts that supplied most passages; earlier ones first on a tie.
        chosen = sorted(by_document.values(), key=len, reverse=True)[:MAX_COMPARED_SOURCES]
        chosen.sort(key=lambda sources: sources[0].number)
        selections = [
            SourceSelection(
                sources[0].citation.document_id,
                tuple(n for n in (_paragraph_number(s) for s in sources) if n),
                sources[0].citation.document_title,
            )
            for sources in chosen
        ]
        return self.compare_sources(selections, research.objective)

    def compare_event_reports(self, event: Event) -> SourceComparison:
        """Compare how the outlets reporting ``event`` cover it (F10 from an
        event view): one report per outlet, up to four, whole."""
        first_by_outlet: dict[str, NewsArticle] = {}
        for report in event.reports:
            first_by_outlet.setdefault(report.outlet, report)
        if len(first_by_outlet) < 2:
            raise AgentError("Only one outlet reported this event, so there is nothing to compare.")
        selections = [
            SourceSelection.of(report, tuple(range(1, len(report.passages()) + 1)) or (1,))
            for report in list(first_by_outlet.values())[:MAX_COMPARED_SOURCES]
        ]
        return self.compare_sources(selections, event.headline)

    def get_comparison(self, comparison_id: UUID) -> SourceComparison:
        comparison = self._require_comparisons().get(comparison_id)
        if comparison is None:
            raise AgentError(f"There is no comparison {comparison_id}.")
        return comparison

    def list_comparisons(self, limit: int = 20) -> list[ComparisonSummary]:
        return self._require_comparisons().list_recent(limit)

    def find_comparison(self, id_prefix: str) -> UUID:
        prefix = id_prefix.strip().lower()
        if not prefix:
            raise AgentError("A comparison id is required.")
        matches = self._require_comparisons().find_ids(prefix)
        if not matches:
            raise AgentError(f"No comparison with id starting '{prefix}'.")
        if len(matches) > 1:
            raise AgentError(f"Id '{prefix}' matches {len(matches)} comparisons; use more characters.")
        return matches[0]

    def _require_comparisons(self) -> ComparisonRepository:
        if self._comparisons is None:
            raise AgentError("Comparisons are not being stored.")
        return self._comparisons

    def _compare(self, selections: list[SourceSelection], subject: str) -> SourceComparison:
        selections = list(dict.fromkeys(selections))
        if len({s.document_id for s in selections}) < 2:
            raise AgentError("Choose at least two different sources to compare.")
        if len(selections) > MAX_COMPARED_SOURCES:
            raise AgentError(f"Compare at most {MAX_COMPARED_SOURCES} sources at a time.")
        subject = " ".join(subject.split())
        if not subject and any(not s.paragraphs for s in selections):
            raise AgentError(
                "Say what to compare the sources on, or name the paragraphs to compare."
            )

        profile = self._profiles.get_profile()
        session = ResearchSession(subject or SELECTED_PASSAGES)
        context = ResearchContext(session, self._tools, profile=profile)
        # The reader's words, and the model's keywords for them, are searched.
        usage = _Usage()
        by_subject = any(not s.paragraphs for s in selections)
        keywords = tuple(self._search_terms(subject, usage)) if by_subject else ()
        CompareSourcesCommand(
            subject or SELECTED_PASSAGES, tuple(selections), keywords=keywords
        ).execute(context)
        warnings = list(session.warnings)

        groups = _passages_by_source(context.corpus)
        profiles = tuple(SourceProfile.of(document) for document, _ in groups)
        passages = tuple(context.corpus.sources)

        def result(**fields) -> SourceComparison:
            fields.setdefault("tokens_used", usage.tokens)
            return SourceComparison(
                subject or SELECTED_PASSAGES, profiles, passages,
                warnings=tuple(warnings), **fields,
            )

        if len(groups) < 2:
            warnings.append(TOO_FEW_TO_COMPARE)
            return result()
        if self._llm is None:
            warnings.append(NO_LLM_WARNING)
            return result()

        prompt = self._prompts.build_comparison_prompt(
            subject or SELECTED_PASSAGES,
            [(source.describe(), passages) for source, (_, passages) in zip(profiles, groups)],
            profile,
        )
        try:
            response = self._llm.generate(prompt)
        except LLMError as exc:
            warnings.append(f"The comparison could not be generated: {exc}")
            return result(tokens_used=usage.tokens)

        parsed = parse_comparison(response.text)
        if parsed is None:
            warnings.append(COMPARISON_UNREADABLE)
            return result(tokens_used=usage.tokens + response.total_tokens)
        source_of = {source.number: source.citation.document_id for source in passages}
        points, dropped = check_points(parsed.points, source_of)
        if dropped:
            warnings.append(
                f"{dropped} point{'s' if dropped != 1 else ''} of the comparison did not "
                f"cite the passages {'they' if dropped != 1 else 'it'} compared and "
                f"{'were' if dropped != 1 else 'was'} left out."
            )
        if parsed.comparability is Comparability.LOW:
            note = parsed.comparability_note.rstrip(".")
            reason = f": {note}." if note else "."
            warnings.insert(0, LOW_COMPARABILITY.format(reason=reason))
        return result(
            points=tuple(points),
            comparability=parsed.comparability,
            comparability_note=parsed.comparability_note,
            uncertainties=parsed.uncertainties,
            personalized=reader_context(profile) is not None,
            tokens_used=usage.tokens + response.total_tokens,
        )

    # --- F04: source-first question answering ------------------------------

    def answer_question(
        self, question: str, preferences: RequestPreferences | None = None
    ) -> AgentResponse:
        """Passages that address ``question``, then an explanation that
        cites them (F04). ``preferences`` override the reader's explanation
        depth or personalization for this request (F14)."""
        question = question.strip()
        if not question:
            raise AgentError("Ask a question first.")

        profile = self._personalization.profile_for(preferences)
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


def _added(count: int) -> str:
    return f"+{count} source{'s' if count != 1 else ''}"


def _paragraph_number(source: Source) -> int | None:
    digits = source.citation.locator.lstrip("¶")
    return int(digits) if digits.isdigit() else None


def _passages_by_source(corpus: ResearchCorpus) -> list[tuple[Document, list[Source]]]:
    """The corpus's passages grouped by document, in the order first added."""
    documents = {document.id: document for document in corpus.documents}
    groups: dict[UUID, list[Source]] = {}
    for source in corpus.sources:
        groups.setdefault(source.citation.document_id, []).append(source)
    return [(documents[document_id], sources) for document_id, sources in groups.items()]


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


def _restore_corpus(result: ResearchResult) -> ResearchCorpus:
    """The corpus of an earlier round, with every source under its old number."""
    corpus = ResearchCorpus()
    for source in result.sources:
        restored = corpus.add_citation(source.passage, source.citation)
        if restored.number != source.number:
            raise AgentError("The stored research session's sources are out of order.")
    return corpus
