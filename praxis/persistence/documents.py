"""Storage for the reading library's documents."""

from __future__ import annotations

import json
import re
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from praxis.documents import Article, Book, Document, NewsArticle, Passage
from praxis.persistence.database import Database

_KINDS: dict[str, type[Document]] = {
    cls.kind: cls for cls in (Document, Book, Article, NewsArticle)
}
_SEARCHED_COLUMNS = ("title", "author", "topics", "text")
_METADATA_COLUMNS = (
    "id, kind, title, author, '' AS text, publication_date, source_url, "
    "license, downloadable, topics, outlet"
)

# Paragraphs shorter than this are headings, title pages and credits rather
# than argument, so they are not offered as evidence.
MIN_INDEXED_WORDS = 8

# Words that say nothing about what a question is about. Without this, "what
# did Marx say about the state" would rank passages by "what" and "about".
_STOPWORDS = frozenset(
    """a about above after again against all am an and any are as at be
    because been before being below between both but by can could did do
    does doing down during each explain few for from further had has have
    having he her here hers him his how i if in into is it its itself just
    me more most my no nor not now of off on once only or other our ours
    out over own same she should so some such tell than that the their
    them then there these they this those through to too under until up
    us very was we were what when where which while who whom why will
    with would you your""".split()
)


@dataclass(frozen=True)
class PassageMatch:
    """A passage found by full-text search.

    ``document`` carries the source's metadata for citing it; its ``text``
    is left empty so a search never loads whole books.
    """

    passage: Passage
    document: Document
    score: float  # higher is more relevant


class DocumentRepository(ABC):
    @abstractmethod
    def find_by_id(self, document_id: UUID) -> Document | None: ...

    @abstractmethod
    def search(self, query: str) -> list[Document]:
        """Documents matching every term of ``query``; title matches first."""

    @abstractmethod
    def search_passages(
        self, query: str, limit: int = 5, document_id: UUID | None = None
    ) -> list[PassageMatch]:
        """Passages relevant to any significant word of ``query``, most
        relevant first. Common words like "what" or "the" are ignored.
        With ``document_id``, only that document's passages are searched."""

    @abstractmethod
    def find_ids_by_prefix(self, prefix: str) -> list[UUID]:
        """Ids of documents whose id starts with ``prefix``. Only ids are
        read, so resolving a short id does not load any document text."""

    @abstractmethod
    def count(self, kind: str | None = None) -> int:
        """How many documents are stored, or how many of one kind."""

    @abstractmethod
    def list_all(self) -> list[Document]:
        """Every stored document, ordered by title."""

    @abstractmethod
    def save(self, document: Document) -> None:
        """Insert the document, or replace the stored copy with the same id."""

    @abstractmethod
    def list_kind(self, kind: str, since: date | None = None) -> list[Document]:
        """Documents of one kind (``"news"``), newest first; with ``since``,
        only those published on or after that date."""


class SQLDocumentRepository(DocumentRepository):
    def __init__(self, database: Database) -> None:
        self._connection = database.connection
        self._index_unindexed_documents()

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

    def search_passages(
        self, query: str, limit: int = 5, document_id: UUID | None = None
    ) -> list[PassageMatch]:
        match = _fts_query(query)
        if match is None or limit < 1:
            return []
        within, parameters = "", [match]
        if document_id is not None:
            within = " AND document_id = ?"
            parameters.append(str(document_id))
        # bm25() is lower for better matches, so ascending order is best first.
        rows = self._connection.execute(
            "SELECT text, passage_id, document_id, locator, "
            "bm25(passage_index) AS rank FROM passage_index "
            f"WHERE passage_index MATCH ?{within} ORDER BY rank LIMIT ?",
            (*parameters, limit),
        ).fetchall()
        documents = self._find_metadata({row["document_id"] for row in rows})
        return [
            PassageMatch(
                passage=Passage(
                    id=UUID(row["passage_id"]),
                    document_id=UUID(row["document_id"]),
                    text=row["text"],
                    locator=row["locator"],
                ),
                document=documents[row["document_id"]],
                score=-row["rank"],
            )
            for row in rows
            if row["document_id"] in documents
        ]

    def find_ids_by_prefix(self, prefix: str) -> list[UUID]:
        rows = self._connection.execute(
            "SELECT id FROM documents WHERE id LIKE ? ESCAPE '\\'",
            (f"{_escape_like(prefix.lower())}%",),
        ).fetchall()
        return [UUID(row["id"]) for row in rows]

    def count(self, kind: str | None = None) -> int:
        if kind is None:
            return self._connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        return self._connection.execute(
            "SELECT COUNT(*) FROM documents WHERE kind = ?", (kind,)
        ).fetchone()[0]

    def list_all(self) -> list[Document]:
        rows = self._connection.execute(
            "SELECT * FROM documents ORDER BY title COLLATE NOCASE"
        ).fetchall()
        return [_to_document(row) for row in rows]

    def list_kind(self, kind: str, since: date | None = None) -> list[Document]:
        where, parameters = "kind = ?", [kind]
        if since is not None:
            where += " AND publication_date >= ?"
            parameters.append(since.isoformat())
        rows = self._connection.execute(
            f"SELECT * FROM documents WHERE {where} "
            "ORDER BY publication_date DESC, title COLLATE NOCASE",
            parameters,
        ).fetchall()
        return [_to_document(row) for row in rows]

    def save(self, document: Document) -> None:
        with self._connection:  # document and its index change together
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
            self._index_passages(document)

    # --- passage index ----------------------------------------------------

    def _index_passages(self, document: Document) -> None:
        """Replace the document's indexed passages. Caller holds the transaction."""
        self._connection.execute(
            "DELETE FROM passage_index WHERE document_id = ?", (str(document.id),)
        )
        self._connection.executemany(
            "INSERT INTO passage_index (text, passage_id, document_id, locator) "
            "VALUES (?,?,?,?)",
            [
                (p.text, str(p.id), str(p.document_id), p.locator)
                for p in document.passages()
                if len(p.text.split()) >= MIN_INDEXED_WORDS
            ],
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO indexed_documents VALUES (?)", (str(document.id),)
        )

    def _index_unindexed_documents(self) -> None:
        """Index documents stored before the passage index existed.

        Runs whenever a repository is created, so it must stay cheap: the
        anti-join uses indexed_documents' primary key, never passage_index.
        """
        rows = self._connection.execute(
            "SELECT documents.* FROM documents LEFT JOIN indexed_documents "
            "ON indexed_documents.document_id = documents.id "
            "WHERE indexed_documents.document_id IS NULL"
        ).fetchall()
        if not rows:
            return
        with self._connection:
            for row in rows:
                self._index_passages(_to_document(row))

    def _find_metadata(self, ids: set[str]) -> dict[str, Document]:
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = self._connection.execute(
            f"SELECT {_METADATA_COLUMNS} FROM documents WHERE id IN ({placeholders})",
            list(ids),
        ).fetchall()
        return {row["id"]: _to_document(row) for row in rows}


def _fts_query(query: str) -> str | None:
    """Turn free text into an FTS5 query matching any significant word.

    Each word is quoted, so punctuation and FTS operators typed by the user
    ("AND", "NEAR", quotes) are searched for as plain words, never parsed.
    """
    words = [w for w in re.findall(r"\w+", query.lower()) if w not in _STOPWORDS]
    if not words:
        return None
    return " OR ".join(f'"{word}"' for word in dict.fromkeys(words))


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
