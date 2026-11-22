"""Storage for news events (F01, F02).

An event is stored with the ids of its reports; the reports themselves
are news documents in the document table. Storing the card means a
dashboard rebuilt from the same reports reuses its summary instead of
asking the model again, and that an event can be opened by its id later
(F02).

Import this module as ``praxis.persistence.events``.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from uuid import UUID

from praxis.documents import NewsArticle
from praxis.news.events import Event, Grouping, SummaryStatus
from praxis.persistence.database import Database
from praxis.persistence.documents import DocumentRepository


class EventRepository(ABC):
    @abstractmethod
    def save(self, event: Event) -> None: ...

    @abstractmethod
    def get(self, event_id: UUID) -> Event | None:
        """The stored event, or None if it is unknown or one of its reports
        is no longer stored."""

    @abstractmethod
    def find_ids(self, prefix: str) -> list[UUID]: ...


class SQLEventRepository(EventRepository):
    def __init__(self, database: Database, documents: DocumentRepository) -> None:
        self._connection = database.connection
        self._documents = documents

    def save(self, event: Event) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO news_events VALUES (?,?,?,?,?)",
                (
                    str(event.id),
                    event.headline,
                    event.last_date.isoformat() if event.last_date else None,
                    len(event.reports),
                    json.dumps({
                        "reports": [str(r.id) for r in event.reports],
                        "grouping": event.grouping.value,
                        "title": event.title,
                        "summary": event.summary,
                        "categories": list(event.categories),
                        "summary_status": event.summary_status.value,
                        "note": event.note,
                    }),
                ),
            )

    def get(self, event_id: UUID) -> Event | None:
        row = self._connection.execute(
            "SELECT data FROM news_events WHERE id = ?", (str(event_id),)
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row["data"])
        reports = [self._documents.find_by_id(UUID(r)) for r in data["reports"]]
        if not all(isinstance(r, NewsArticle) for r in reports):
            return None
        return Event(
            tuple(reports),
            Grouping(data["grouping"]),
            title=data["title"],
            summary=data["summary"],
            categories=tuple(data["categories"]),
            summary_status=SummaryStatus(data["summary_status"]),
            note=data["note"],
            id=event_id,
        )

    def find_ids(self, prefix: str) -> list[UUID]:
        prefix = prefix.strip().lower()
        if not prefix or any(ch not in "0123456789abcdef-" for ch in prefix):
            return []
        rows = self._connection.execute(
            "SELECT id FROM news_events WHERE id LIKE ?", (prefix + "%",)
        ).fetchall()
        return [UUID(row["id"]) for row in rows]
