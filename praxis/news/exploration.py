"""The expanded view of one event (F02, UC02; SD03's ``openEvent``).

``EventExplorer.explore`` gathers more than the dashboard card shows:
other stored reports that look related but were not grouped with the
event, and library passages that may give historical or theoretical
background. It then asks the model for a longer account that cites the
reports and passages as [n], sets out where the reports differ instead of
resolving it (UC02: "the disagreement is shown rather than silently
resolved"), and lists what the reports leave open.

Whether the event is still developing is decided from its dates, not by
the model (UC02: "the system indicates that available information may
change").
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from uuid import uuid5

from praxis.agent.corpus import ResearchCorpus, Source, cited_numbers
from praxis.agent.prompts import PromptBuilder
from praxis.documents import NewsArticle, Passage
from praxis.llm import LLMClient, LLMError
from praxis.news.clustering import related_reports
from praxis.news.events import Event
from praxis.persistence import DocumentRepository

# Reports dated within this many days of the event's latest report may be related.
RELATED_DAYS = 3
MAX_RELATED = 4
MAX_LIBRARY_PASSAGES = 3
SEARCH_LIMIT = 30
# An event whose latest report is this recent may still change.
DEVELOPING_DAYS = 1

NO_LLM = "No language model is configured, so only the reports and passages are shown."
NO_LIBRARY_CONTEXT = "No library passage was found that bears on this event."
UNKNOWN_SOURCES = "The account refers to {labels}, which {verb} not among the reports and passages; treat those statements as unsupported."
UNCITED = "The account cites none of the reports; treat it as unsupported."


@dataclass
class ExpandedEvent:
    """What the expanded event view shows.

    ``sources`` number the event's reports first ([1] … [k], in the
    event's order), then the library passages. ``related`` are other
    reports that may concern the same event; they are listed, not cited.
    """

    event: Event
    sources: tuple[Source, ...]
    report_count: int
    related: tuple[NewsArticle, ...] = ()
    account: str = ""
    open_questions: tuple[str, ...] = ()
    cited: tuple[Source, ...] = ()
    developing: bool = False
    warnings: tuple[str, ...] = ()
    tokens_used: int = 0
    search_terms: tuple[str, ...] = field(default=())

    @property
    def report_sources(self) -> tuple[Source, ...]:
        return self.sources[: self.report_count]

    @property
    def library_sources(self) -> tuple[Source, ...]:
        return self.sources[self.report_count :]


class EventExplorer:
    def __init__(
        self,
        documents: DocumentRepository,
        llm: LLMClient | None = None,
        prompts: PromptBuilder | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._documents = documents
        self._llm = llm
        self._prompts = prompts or PromptBuilder()
        self._today = today

    def explore(self, event: Event) -> ExpandedEvent:
        warnings: list[str] = []
        tokens = 0
        corpus = ResearchCorpus()
        for report in event.reports:
            corpus.add_passage(report, report_passage(report))
        report_count = len(corpus)

        query = " ".join(r.title for r in event.reports)
        related = self._related_reports(event)

        terms: list[str] = []
        if self._llm is not None:
            try:
                response = self._llm.generate(self._prompts.build_search_terms_prompt(
                    f"Historical and theoretical background to this news event: {event.headline}"
                ))
                tokens += response.total_tokens
                terms = self._prompts.parse_search_terms(response.text)
            except LLMError:
                pass  # the headline is still searched
        for match in self._library_passages(", ".join(terms) or query):
            corpus.add_passage(match.document, match.passage)
        if len(corpus) == report_count:
            warnings.append(NO_LIBRARY_CONTEXT)

        expanded = ExpandedEvent(
            event, tuple(corpus.sources), report_count, tuple(related),
            developing=self.is_developing(event), tokens_used=tokens, search_terms=tuple(terms),
        )
        if self._llm is None:
            expanded.warnings = (*warnings, NO_LLM)
            return expanded
        return self._write_account(expanded, corpus, warnings)

    def is_developing(self, event: Event) -> bool:
        last = event.last_date
        return last is not None and last >= self._today() - timedelta(days=DEVELOPING_DAYS)

    def _related_reports(self, event: Event) -> list[NewsArticle]:
        """Stored reports from around the same days that resemble the
        event's reports but were not grouped with it."""
        last = event.last_date or self._today()
        nearby = [
            d for d in self._documents.list_kind(NewsArticle.kind, last - timedelta(days=RELATED_DAYS))
            if isinstance(d, NewsArticle)
            and d.publication_date is not None
            and d.publication_date <= last + timedelta(days=RELATED_DAYS)
        ]
        return related_reports(event, nearby, MAX_RELATED)

    def _library_passages(self, query: str):
        matches = [
            m for m in self._documents.search_passages(query, SEARCH_LIMIT)
            if not isinstance(m.document, NewsArticle)
        ]
        return matches[:MAX_LIBRARY_PASSAGES]

    def _write_account(
        self, expanded: ExpandedEvent, corpus: ResearchCorpus, warnings: list[str]
    ) -> ExpandedEvent:
        reports = [
            (s.label, r.outlet, r.publication_date.isoformat() if r.publication_date else "undated", r.title, r.text)
            for s, r in zip(expanded.report_sources, expanded.event.reports)
        ]
        passages = [(s.label, s.citation.format(), s.citation.quoted_text) for s in expanded.library_sources]
        prompt = self._prompts.build_event_exploration_prompt(
            expanded.event.headline, reports, passages, expanded.developing
        )
        try:
            response = self._llm.generate(prompt)
        except LLMError as exc:
            expanded.warnings = (*warnings, f"The expanded account could not be generated: {exc}")
            return expanded
        expanded.tokens_used += response.total_tokens

        account, questions = self._prompts.split_open_questions(response.text)
        numbers = cited_numbers(account)
        unknown = [n for n in numbers if not corpus.has_source(n)]
        if unknown:
            warnings.append(UNKNOWN_SOURCES.format(
                labels=", ".join(f"[{n}]" for n in unknown), verb="is" if len(unknown) == 1 else "are",
            ))
        if not any(1 <= n <= expanded.report_count for n in numbers):
            warnings.append(UNCITED)
        expanded.account = account
        expanded.open_questions = tuple(questions)
        expanded.cited = tuple(corpus.source(n) for n in numbers if corpus.has_source(n))
        expanded.warnings = tuple(warnings)
        return expanded


def report_passage(report: NewsArticle) -> Passage:
    """The report's summary as one citable passage; its headline if the
    feed gave no summary."""
    passages = report.passages()
    if passages:
        return passages[0] if len(passages) == 1 else Passage(
            passages[0].id, report.id, "\n\n".join(p.text for p in passages), passages[0].locator
        )
    return Passage(uuid5(report.id, "headline"), report.id, report.title, "headline")
