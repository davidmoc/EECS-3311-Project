"""Storage for annotations (F06, UC06 postcondition: "any generated
annotation is associated with the appropriate passage").

Annotations are keyed by passage id. Passage ids are derived from the
document id and paragraph number (``Document.passages``), so an annotation
finds its passage again every time the text is opened.

The sources an annotation drew on are stored as JSON beside it, with their
quoted text, so the annotation can still be shown with its sources if one
of those texts later leaves the library.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from praxis.documents import Annotation, AnnotationType, Citation
from praxis.persistence.database import Database


class AnnotationRepository(ABC):
    @abstractmethod
    def save(self, annotation: Annotation) -> None: ...

    @abstractmethod
    def for_passage(self, passage_id: UUID) -> list[Annotation]:
        """The passage's annotations, oldest first."""

    @abstractmethod
    def for_document(self, document_id: UUID) -> list[Annotation]:
        """All of a document's annotations, in text order, oldest first
        within a paragraph."""

    @abstractmethod
    def find_ids(self, prefix: str) -> list[UUID]:
        """Ids of the annotations whose id starts with ``prefix``."""

    @abstractmethod
    def delete(self, annotation_id: UUID) -> bool:
        """Remove the annotation; False if there was none with that id."""


class SQLAnnotationRepository(AnnotationRepository):
    def __init__(self, database: Database) -> None:
        self._connection = database.connection

    def save(self, annotation: Annotation) -> None:
        if annotation.document_id is None:
            raise ValueError("Only annotations of a library document can be stored.")
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO annotations VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(annotation.id),
                    str(annotation.passage_id),
                    str(annotation.document_id),
                    _paragraph_number(annotation.locator),
                    annotation.type.value,
                    annotation.content,
                    annotation.created_at.isoformat(),
                    int(annotation.personalized),
                    json.dumps({
                        "locator": annotation.locator,
                        "uncertainties": list(annotation.uncertainties),
                        "sources": [_encode_citation(c) for c in annotation.sources],
                    }),
                ),
            )

    def for_passage(self, passage_id: UUID) -> list[Annotation]:
        rows = self._connection.execute(
            "SELECT * FROM annotations WHERE passage_id = ? ORDER BY created_at",
            (str(passage_id),),
        ).fetchall()
        return [_to_annotation(row) for row in rows]

    def for_document(self, document_id: UUID) -> list[Annotation]:
        rows = self._connection.execute(
            "SELECT * FROM annotations WHERE document_id = ? "
            "ORDER BY paragraph, created_at",
            (str(document_id),),
        ).fetchall()
        return [_to_annotation(row) for row in rows]

    def find_ids(self, prefix: str) -> list[UUID]:
        prefix = prefix.strip().lower()
        # Ids are hex and dashes, so a valid prefix holds no LIKE wildcard.
        if not prefix or any(ch not in "0123456789abcdef-" for ch in prefix):
            return []
        rows = self._connection.execute(
            "SELECT id FROM annotations WHERE id LIKE ?", (prefix + "%",)
        ).fetchall()
        return [UUID(row["id"]) for row in rows]

    def delete(self, annotation_id: UUID) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM annotations WHERE id = ?", (str(annotation_id),)
            )
        return cursor.rowcount > 0


def _paragraph_number(locator: str) -> int:
    """``"¶12"`` → 12, so annotations sort in text order; 0 if not a ¶."""
    digits = locator.lstrip("¶")
    return int(digits) if digits.isdigit() else 0


def _encode_citation(citation: Citation) -> dict[str, str]:
    return {
        "id": str(citation.id),
        "document_id": str(citation.document_id),
        "document_title": citation.document_title,
        "author": citation.author,
        "locator": citation.locator,
        "quoted_text": citation.quoted_text,
    }


def _decode_citation(data: dict[str, str]) -> Citation:
    return Citation(
        id=UUID(data["id"]),
        document_id=UUID(data["document_id"]),
        document_title=data["document_title"],
        author=data["author"],
        locator=data["locator"],
        quoted_text=data["quoted_text"],
    )


def _to_annotation(row) -> Annotation:
    extra = json.loads(row["data"])
    return Annotation(
        id=UUID(row["id"]),
        passage_id=UUID(row["passage_id"]),
        document_id=UUID(row["document_id"]),
        locator=extra["locator"],
        type=AnnotationType(row["type"]),
        content=row["content"],
        created_at=datetime.fromisoformat(row["created_at"]),
        personalized=bool(row["personalized"]),
        uncertainties=tuple(extra["uncertainties"]),
        sources=tuple(_decode_citation(c) for c in extra["sources"]),
    )
