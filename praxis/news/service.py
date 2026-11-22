"""Fetching and keeping current news (F01, SD03's ``NewsService``).

``refresh`` asks every configured provider for its articles and stores
them. One unavailable source does not stop the others; which sources
failed is reported, so the dashboard can say its information is limited
(UC01: "If one news source is unavailable, the system continues using
available sources").

Stored articles are what the dashboard shows, so earlier news is still
available when no source can be reached (UC01: "previously cached
information where available").

Imported as ``praxis.news.service``: it uses ``praxis.persistence``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from praxis.documents import NewsArticle
from praxis.news.clustering import EventClusterer
from praxis.news.events import Event, SummaryStatus
from praxis.news.exploration import EventExplorer, ExpandedEvent
from praxis.news.providers import NewsProvider, NewsProviderError
from praxis.news.summary import NewsSummaryService
from praxis.persistence import DocumentRepository
from praxis.persistence.events import EventRepository

DEFAULT_DAYS = 3
DEFAULT_EVENTS = 8

NO_NEWS_REACHED = "No news source could be reached, so the dashboard shows news stored earlier."
LIMITED_NEWS = "Some news sources were unavailable ({outlets}), so the dashboard may be incomplete."
NO_MODEL = "No language model is configured, so events are shown with their headlines only."
NOT_STORED = "Some events could not be stored, so they cannot be opened later: {}"

Today = Callable[[], date]


class NewsError(ValueError):
    """A news request could not be completed; the message says why."""


@dataclass(frozen=True)
class NewsRefresh:
    """What one refresh fetched, and from where it could not."""

    fetched: tuple[NewsArticle, ...]
    new_count: int
    failures: tuple[tuple[str, str], ...]  # (outlet, reason)
    source_count: int

    @property
    def is_limited(self) -> bool:
        """Some, but not all, sources could not be reached."""
        return bool(self.failures) and len(self.failures) < self.source_count

    @property
    def all_failed(self) -> bool:
        return self.source_count > 0 and len(self.failures) == self.source_count


@dataclass(frozen=True)
class Dashboard:
    """What the dashboard shows (SD03's "dashboard events"), and why it
    may be limited."""

    events: tuple[Event, ...]
    total_events: int
    refresh: NewsRefresh | None = None
    warnings: tuple[str, ...] = ()
    tokens_used: int = 0


class NewsService:
    def __init__(
        self,
        providers: list[NewsProvider],
        documents: DocumentRepository,
        today: Today = date.today,
        clusterer: EventClusterer | None = None,
        summaries: NewsSummaryService | None = None,
        events: EventRepository | None = None,
        explorer: EventExplorer | None = None,
    ) -> None:
        """Without ``summaries`` events show their headlines only; without
        ``events`` they are not stored, so summaries are not reused."""
        self._providers = list(providers)
        self._documents = documents
        self._today = today
        self._clusterer = clusterer or EventClusterer()
        self._summaries = summaries or NewsSummaryService(None)
        self._events = events
        self._explorer = explorer or EventExplorer(documents, today=today)

    def get_dashboard_events(
        self, days: int = DEFAULT_DAYS, limit: int = DEFAULT_EVENTS, refresh: bool = True
    ) -> Dashboard:
        """SD03's ``getDashboardEvents``: fetch, group, summarise.

        The ``limit`` events reported by most outlets are shown. Events with
        two or more reports get a model-written card, reused from storage
        when the same reports were summarised before; a single report is
        shown with its outlet's own summary.
        """
        warnings: list[str] = []
        outcome = self.refresh() if refresh else None
        if outcome is not None and outcome.all_failed:
            warnings.append(NO_NEWS_REACHED)
        elif outcome is not None and outcome.is_limited:
            warnings.append(LIMITED_NEWS.format(outlets=", ".join(o for o, _ in outcome.failures)))

        grouped = self._clusterer.cluster(self.get_recent_news(days))
        if any(len(e.reports) > 1 for e in grouped[:limit]) and not self._summaries.available:
            warnings.append(NO_MODEL)
        shown, tokens = [], 0
        for event in grouped[:limit]:
            card, used = self._card(event)
            shown.append(card)
            tokens += used
            try:
                self._store(card)
            except sqlite3.Error as exc:
                if not any(w.startswith("Some events could not be stored") for w in warnings):
                    warnings.append(NOT_STORED.format(exc))
        return Dashboard(tuple(shown), len(grouped), outcome, tuple(warnings), tokens)

    def get_event(self, event_id: UUID) -> Event:
        """SD03's ``getEvent``: a stored event by id."""
        event = self._events.get(event_id) if self._events else None
        if event is None:
            raise NewsError(f"There is no stored event {event_id}.")
        return event

    def get_expanded_event(self, event_id: UUID) -> ExpandedEvent:
        """F02: the event with related reports, library background and a
        longer account of it."""
        return self._explorer.explore(self.get_event(event_id))

    def find_event(self, id_prefix: str) -> UUID:
        prefix = id_prefix.strip().lower()
        if not prefix:
            raise NewsError("An event id is required.")
        matches = self._events.find_ids(prefix) if self._events else []
        if not matches:
            raise NewsError(f"No event with id starting '{prefix}'. Event ids are shown by `news dashboard`.")
        if len(matches) > 1:
            raise NewsError(f"Id '{prefix}' matches {len(matches)} events; use more characters.")
        return matches[0]

    def _card(self, event: Event) -> tuple[Event, int]:
        """The event ready to show, and the tokens spent on it."""
        if len(event.reports) == 1:
            return event, 0
        stored = self._events.get(event.id) if self._events else None
        if stored is not None and stored.summary_status is SummaryStatus.SUMMARIZED:
            return stored, 0
        outcome = self._summaries.summarize(event)
        return outcome.event, outcome.tokens_used

    def _store(self, event: Event) -> None:
        """Keep the event so it can be opened by id (F02)."""
        if self._events is not None:
            self._events.save(event)

    @property
    def outlets(self) -> list[str]:
        return [provider.name for provider in self._providers]

    def refresh(self) -> NewsRefresh:
        """Fetch from every provider and store what they return."""
        fetched: dict = {}
        failures: list[tuple[str, str]] = []
        for provider in self._providers:
            try:
                articles = provider.get_recent_news()
            except NewsProviderError as exc:
                failures.append((provider.name, str(exc)))
                continue
            for article in articles:
                fetched.setdefault(article.id, article)
        new = 0
        for article in fetched.values():
            if self._documents.find_by_id(article.id) is None:
                new += 1
            self._documents.save(article)
        return NewsRefresh(tuple(fetched.values()), new, tuple(failures), len(self._providers))

    def get_recent_news(self, days: int = DEFAULT_DAYS) -> list[NewsArticle]:
        """Stored articles published in the last ``days`` days (today
        included), newest first. Articles without a date are left out:
        nothing says they are current."""
        if days < 1:
            raise ValueError("Show at least one day of news.")
        since = self._today() - timedelta(days=days - 1)
        return [a for a in self._documents.list_kind(NewsArticle.kind, since) if isinstance(a, NewsArticle)]
