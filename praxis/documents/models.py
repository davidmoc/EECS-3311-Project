"""Source material: documents, the passages inside them, and references to both.

The platform is source-first, so these classes carry the rules that keep
sources honest: passages have stable identities, citations always point back
at a real passage, and how much text may be quoted depends on the licence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import ClassVar
from uuid import UUID, uuid4, uuid5

# Licences under which a text may be reproduced in full inside the app.
REPRODUCIBLE_LICENSES = ("public domain", "cc0", "cc by", "cc by-sa")

# Longest quotation taken from a text that may not be reproduced in full.
EXCERPT_LIMIT = 300


class AnnotationType(Enum):
    TERMINOLOGY = "terminology"
    HISTORICAL_CONTEXT = "historical_context"
    ARGUMENT = "argument"
    FRAMING = "framing"
    FACT_CHECK = "fact_check"
    CONNECTION = "connection"


@dataclass(frozen=True)
class Passage:
    id: UUID
    document_id: UUID
    text: str
    locator: str


@dataclass(frozen=True)
class Citation:
    document_id: UUID
    document_title: str
    author: str
    locator: str
    quoted_text: str
    id: UUID = field(default_factory=uuid4)

    def format(self) -> str:
        return f"{self.author}, “{self.document_title}”, {self.locator}"


@dataclass(frozen=True)
class Annotation:
    """AI-generated commentary attached to a passage.

    Kept as its own object, never merged into the passage text, so the
    author's words and the agent's commentary stay distinguishable.
    """

    passage_id: UUID
    type: AnnotationType
    content: str
    id: UUID = field(default_factory=uuid4)


@dataclass
class Document:
    title: str
    author: str
    text: str = ""
    publication_date: date | None = None
    source_url: str = ""
    license: str = ""
    downloadable: bool = False
    topics: tuple[str, ...] = ()
    id: UUID = field(default_factory=uuid4)

    kind: ClassVar[str] = "document"

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("A document must have a title.")
        self.topics = tuple(self.topics)

    def can_reproduce(self) -> bool:
        """Whether the full text may be shown or downloaded in the app."""
        normalized = self.license.strip().lower()
        return any(normalized.startswith(name) for name in REPRODUCIBLE_LICENSES)

    def passages(self) -> list[Passage]:
        """Split the text into paragraph passages.

        Passage ids are derived from the document id and paragraph number, so
        the same passage gets the same id every time the document is loaded.
        Annotations and saved items rely on that.
        """
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", self.text)]
        return [
            Passage(
                id=uuid5(self.id, str(number)),
                document_id=self.id,
                text=paragraph,
                locator=f"¶{number}",
            )
            for number, paragraph in enumerate(
                (p for p in paragraphs if p), start=1
            )
        ]

    def find_passages(self, query: str) -> list[Passage]:
        """Passages containing every term of ``query``, ignoring case."""
        terms = query.lower().split()
        if not terms:
            return []
        return [
            passage
            for passage in self.passages()
            if all(term in passage.text.lower() for term in terms)
        ]

    def cite(self, passage: Passage) -> Citation:
        """Create a citation for one of this document's passages.

        Texts that may not be reproduced in full are quoted only up to
        ``EXCERPT_LIMIT`` characters.
        """
        if passage.document_id != self.id:
            raise ValueError("Passage does not belong to this document.")
        quoted = passage.text
        if not self.can_reproduce() and len(quoted) > EXCERPT_LIMIT:
            quoted = quoted[:EXCERPT_LIMIT].rstrip() + "…"
        return Citation(
            document_id=self.id,
            document_title=self.title,
            author=self.author,
            locator=passage.locator,
            quoted_text=quoted,
        )


@dataclass
class Book(Document):
    kind: ClassVar[str] = "book"


@dataclass
class Article(Document):
    kind: ClassVar[str] = "article"


@dataclass
class NewsArticle(Article):
    outlet: str = ""

    kind: ClassVar[str] = "news"
