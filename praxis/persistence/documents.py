"""Storage for the reading library's documents."""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import date
from uuid import UUID

from praxis.documents import Article, Book, Document, NewsArticle
from praxis.persistence.database import Database

_KINDS: dict[str, type[Document]] = {
    cls.kind: cls for cls in (Document, Book, Article, NewsArticle)
}
_SEARCHED_COLUMNS = ("title", "author", "topics", "text")


class DocumentRepository(ABC):
    @abstractmethod
    def find_by_id(self, document_id: UUID) -> Document | None: ...

    @abstractmethod
    def search(self, query: str) -> list[Document]:
        """Documents matching every term of ``query``; title matches first."""

    @abstractmethod
    def save(self, document: Document) -> None:
        """Insert the document, or replace the stored copy with the same id."""


class SQLDocumentRepository(DocumentRepository):
    def __init__(self, database: Database) -> None:
        self._connection = database.connection

    def find_by_id(self, document_id: UUID) -> Document | None:
        row = self._connection.execute(
            "SELECT * FROM documents WHERE id = ?", (str(document_id),)
        ).fetchone()
        return _to_document(row) if row else None

    def search(self, query: str) -> list[Document]:
        terms = query.split()
        if not terms:
            return []

        patterns = [f"%{_escape_like(term)}%" for term in terms]
        any_column = " OR ".join(
            f"{column} LIKE ? ESCAPE '\\'" for column in _SEARCHED_COLUMNS
        )
        where = " AND ".join(f"({any_column})" for _ in terms)
        in_title = " + ".join("(title LIKE ? ESCAPE '\\')" for _ in terms)
        parameters = [
            pattern for pattern in patterns for _ in _SEARCHED_COLUMNS
        ] + patterns

        rows = self._connection.execute(
            f"SELECT * FROM documents WHERE {where} "
            f"ORDER BY {in_title} DESC, title COLLATE NOCASE",
            parameters,
        ).fetchall()
        return [_to_document(row) for row in rows]

    def save(self, document: Document) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(document.id),
                    document.kind,
                    document.title,
                    document.author,
                    document.text,
                    document.publication_date.isoformat()
                    if document.publication_date
                    else None,
                    document.source_url,
                    document.license,
                    int(document.downloadable),
                    json.dumps(list(document.topics)),
                    getattr(document, "outlet", ""),
                ),
            )


def _escape_like(term: str) -> str:
    """Treat the user's ``%`` and ``_`` as literal characters, not wildcards."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _to_document(row: sqlite3.Row) -> Document:
    cls = _KINDS.get(row["kind"], Document)
    fields = dict(
        id=UUID(row["id"]),
        title=row["title"],
        author=row["author"],
        text=row["text"],
        publication_date=date.fromisoformat(row["publication_date"])
        if row["publication_date"]
        else None,
        source_url=row["source_url"],
        license=row["license"],
        downloadable=bool(row["downloadable"]),
        topics=tuple(json.loads(row["topics"])),
    )
    if cls is NewsArticle:
        fields["outlet"] = row["outlet"]
    return cls(**fields)
