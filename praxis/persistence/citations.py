"""JSON encoding of citations, shared by the stores that keep them
(annotations, numbered sources, learning paths).

Depends only on ``praxis.documents``, so the annotation store, which
``praxis.persistence`` exports, can use it without importing the agent.
"""

from __future__ import annotations

from uuid import UUID

from praxis.documents import Citation


def encode_citation(citation: Citation) -> dict[str, str]:
    return {
        "id": str(citation.id),
        "document_id": str(citation.document_id),
        "document_title": citation.document_title,
        "author": citation.author,
        "locator": citation.locator,
        "quoted_text": citation.quoted_text,
    }


def decode_citation(data: dict[str, str]) -> Citation:
    return Citation(
        id=UUID(data["id"]),
        document_id=UUID(data["document_id"]),
        document_title=data["document_title"],
        author=data["author"],
        locator=data["locator"],
        quoted_text=data["quoted_text"],
    )
