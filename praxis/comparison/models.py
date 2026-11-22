"""What a source comparison is made of (F10, UC10, SD06).

``SourceProfile`` says what is known about a source: who wrote or published
it, when, and where it came from. It is built only from the document's own
metadata, so nothing is inferred about ownership or funding that the
library does not record (UC10: "If source-profile information is
unavailable, no unsupported inference is made").

``SourceComparison`` holds the compared passages, numbered [1], [2] across
all sources, and the points the model made about them. Each point cites the
passages it rests on. Factual disagreements are kept apart from differences
in framing (UC10: "the disagreement is distinguished from differences in
framing"), and observations about a source's standpoint are kept apart from
both, because they are interpretation, not fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from praxis.agent.corpus import Source
from praxis.documents import Document


@dataclass(frozen=True)
class SourceSelection:
    """One source the reader chose: a document, and optionally which of its
    paragraphs to compare. With no paragraphs, the passages that best match
    the comparison's subject are used."""

    document_id: UUID
    paragraphs: tuple[int, ...] = ()
    # Only for messages about the source; the id is what identifies it.
    title: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "paragraphs", tuple(self.paragraphs))
        if any(n < 1 for n in self.paragraphs):
            raise ValueError("Paragraph numbers start at 1.")

    @classmethod
    def of(cls, document: Document, paragraphs: tuple[int, ...] = ()) -> SourceSelection:
        return cls(document.id, paragraphs, document.title)

    @property
    def label(self) -> str:
        return self.title or str(self.document_id)[:8]


@dataclass(frozen=True)
class SourceProfile:
    """What the library records about a source, and nothing more."""

    document_id: UUID
    title: str
    author: str
    kind: str
    outlet: str = ""
    publication_date: date | None = None
    source_url: str = ""
    license: str = ""

    @classmethod
    def of(cls, document: Document) -> SourceProfile:
        return cls(
            document_id=document.id,
            title=document.title,
            author=document.author,
            kind=document.kind,
            outlet=getattr(document, "outlet", ""),
            publication_date=document.publication_date,
            source_url=document.source_url,
            license=document.license,
        )

    def describe(self) -> str:
        """``Lenin, “State and Revolution” (book, 1917)`` plus the outlet."""
        details = [self.kind]
        if self.outlet:
            details.append(f"published by {self.outlet}")
        if self.publication_date:
            details.append(str(self.publication_date.year))
        return f"{self.author}, “{self.title}” ({', '.join(details)})"


class Comparability(Enum):
    COMPARABLE = "comparable"
    PARTLY = "partly comparable"
    LOW = "not comparable"
    UNKNOWN = "not assessed"

    @classmethod
    def parse(cls, word: str) -> Comparability | None:
        word = " ".join(word.lower().split())
        if word.startswith(("not", "low", "in")):  # "not comparable", "incomparable"
            return cls.LOW
        if word.startswith("partl"):
            return cls.PARTLY
        if word.startswith("comparable") or word.startswith("high"):
            return cls.COMPARABLE
        return None


class PointKind(Enum):
    SIMILARITY = "similarity"
    DIFFERENCE = "difference"
    # The sources contradict each other about a fact.
    DISAGREEMENT = "disagreement"
    # Interpretation of one source's standpoint or framing.
    OBSERVATION = "observation"


# What a difference can be about (F10: "terminology, emphasis, framing,
# assumptions, included or omitted context, and the evidence or authorities
# relied upon").
DIFFERENCE_ASPECTS = ("terminology", "emphasis", "framing", "assumptions", "omission", "evidence")


@dataclass(frozen=True)
class ComparisonPoint:
    kind: PointKind
    description: str
    evidence: tuple[int, ...] = ()  # passage numbers
    aspect: str = ""  # one of DIFFERENCE_ASPECTS, for differences only

    def with_evidence(self, evidence: tuple[int, ...]) -> ComparisonPoint:
        return ComparisonPoint(self.kind, self.description, evidence, self.aspect)


@dataclass
class SourceComparison:
    """The structured result of comparing two or more sources.

    ``passages`` are numbered across all sources; ``source_of`` says which
    profile each passage number belongs to. ``points`` is empty when the
    model was not asked or could not answer; the passages are still there
    for the reader to compare directly.
    """

    subject: str
    profiles: tuple[SourceProfile, ...]
    passages: tuple[Source, ...]
    points: tuple[ComparisonPoint, ...] = ()
    comparability: Comparability = Comparability.UNKNOWN
    comparability_note: str = ""
    uncertainties: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    personalized: bool = False
    tokens_used: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: UUID = field(default_factory=uuid4)

    def source_of(self, passage_number: int) -> SourceProfile | None:
        passage = next((p for p in self.passages if p.number == passage_number), None)
        if passage is None:
            return None
        return next(
            (s for s in self.profiles if s.document_id == passage.citation.document_id), None
        )

    def passages_of(self, profile: SourceProfile) -> list[Source]:
        return [p for p in self.passages if p.citation.document_id == profile.document_id]

    def points_of(self, kind: PointKind) -> list[ComparisonPoint]:
        return [p for p in self.points if p.kind is kind]

    @property
    def similarities(self) -> list[ComparisonPoint]:
        return self.points_of(PointKind.SIMILARITY)

    @property
    def differences(self) -> list[ComparisonPoint]:
        return self.points_of(PointKind.DIFFERENCE)

    @property
    def disagreements(self) -> list[ComparisonPoint]:
        return self.points_of(PointKind.DISAGREEMENT)

    @property
    def observations(self) -> list[ComparisonPoint]:
        return self.points_of(PointKind.OBSERVATION)

    @property
    def is_comparable(self) -> bool:
        """False only when the model judged the sources not comparable."""
        return self.comparability is not Comparability.LOW

    @property
    def has_analysis(self) -> bool:
        return bool(self.points) or self.comparability is not Comparability.UNKNOWN
