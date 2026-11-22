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

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from praxis.documents import NewsArticle
from praxis.news.providers import NewsProvider, NewsProviderError
from praxis.persistence import DocumentRepository

DEFAULT_DAYS = 3

Today = Callable[[], date]


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


class NewsService:
    def __init__(
        self,
        providers: list[NewsProvider],
        documents: DocumentRepository,
        today: Today = date.today,
    ) -> None:
        self._providers = list(providers)
        self._documents = documents
        self._today = today

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
