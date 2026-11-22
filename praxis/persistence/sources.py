"""JSON encoding of numbered sources, shared by the stores that keep them
(research sessions, source comparisons).

The passage text and its citation are stored whole, so a stored result can
be shown again even if its text later leaves the library.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from praxis.agent.corpus import Source
from praxis.documents import Citation, Passage


def encode_source(source: Source) -> dict[str, Any]:
    passage, citation = source.passage, source.citation
    return {
        "number": source.number,
        "passage": {
            "id": str(passage.id),
            "document_id": str(passage.document_id),
            "text": passage.text,
            "locator": passage.locator,
        },
        "citation": {
            "id": str(citation.id),
            "document_id": str(citation.document_id),
            "document_title": citation.document_title,
            "author": citation.author,
            "locator": citation.locator,
            "quoted_text": citation.quoted_text,
        },
    }


def decode_source(data: dict[str, Any]) -> Source:
    passage, citation = data["passage"], data["citation"]
    return Source(
        data["number"],
        Passage(UUID(passage["id"]), UUID(passage["document_id"]), passage["text"], passage["locator"]),
        Citation(
            UUID(citation["document_id"]),
            citation["document_title"],
            citation["author"],
            citation["locator"],
            citation["quoted_text"],
            UUID(citation["id"]),
        ),
    )
