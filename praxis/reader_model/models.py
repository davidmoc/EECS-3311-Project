"""The reader model (F13): what the system believes about the reader.

Every belief records where it came from. Anything the reader states
themselves outranks what the system inferred from their activity, so a
correction is never silently undone by later inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from uuid import UUID


class KnowledgeLevel(IntEnum):
    """Ordered, so levels can be compared: ``INTRODUCTORY < ADVANCED``."""

    NONE = 0
    INTRODUCTORY = 1
    INTERMEDIATE = 2
    ADVANCED = 3


class AssessmentSource(Enum):
    INFERRED = "inferred"
    USER_STATED = "user_stated"


class ExplanationDepth(Enum):
    BRIEF = "brief"
    STANDARD = "standard"
    DETAILED = "detailed"


def normalize_topic(topic: str) -> str:
    cleaned = " ".join(topic.lower().split())
    if not cleaned:
        raise ValueError("A topic must not be empty.")
    return cleaned


@dataclass
class KnowledgeArea:
    topic: str
    level: KnowledgeLevel
    source: AssessmentSource
    evidence: int = 0  # how many activities support an inferred level

    @property
    def is_inferred(self) -> bool:
        return self.source is AssessmentSource.INFERRED


@dataclass
class KnowledgeProfile:
    areas: dict[str, KnowledgeArea] = field(default_factory=dict)

    def get_level(self, topic: str) -> KnowledgeLevel:
        area = self.areas.get(normalize_topic(topic))
        return area.level if area else KnowledgeLevel.NONE

    def update_level(
        self,
        topic: str,
        level: KnowledgeLevel,
        source: AssessmentSource = AssessmentSource.INFERRED,
    ) -> bool:
        """Record a level for ``topic``. Returns whether anything changed.

        A stated level always replaces what was there. An inferred level
        never overrides a stated one and never lowers an inferred one:
        reading more about a topic is not evidence of knowing less.
        """
        key = normalize_topic(topic)
        current = self.areas.get(key)
        if source is AssessmentSource.USER_STATED:
            self.areas[key] = KnowledgeArea(key, level, source)
            return current is None or current.level != level or current.is_inferred
        if current is not None and not current.is_inferred:
            return False
        evidence = (current.evidence if current else 0) + 1
        new_level = max(level, current.level) if current else level
        self.areas[key] = KnowledgeArea(key, new_level, source, evidence)
        return current is None or new_level != current.level

    def remove(self, topic: str) -> bool:
        return self.areas.pop(normalize_topic(topic), None) is not None

    def identify_blind_spots(
        self, topics: list[str], required: KnowledgeLevel = KnowledgeLevel.INTRODUCTORY
    ) -> list[str]:
        """The topics from ``topics`` the reader is not known to understand
        at ``required`` level, in the order given."""
        return [t for t in topics if self.get_level(t) < required]


@dataclass
class InterestProfile:
    weights: dict[str, float] = field(default_factory=dict)
    # Interests the reader removed; inference must not bring them back.
    dismissed: set[str] = field(default_factory=set)

    def add(self, topic: str, weight: float = 1.0, stated: bool = False) -> None:
        key = normalize_topic(topic)
        if stated:
            self.dismissed.discard(key)
        elif key in self.dismissed:
            return
        self.weights[key] = self.weights.get(key, 0.0) + weight

    def remove(self, topic: str) -> bool:
        key = normalize_topic(topic)
        self.dismissed.add(key)
        return self.weights.pop(key, None) is not None

    def top(self, count: int = 5) -> list[str]:
        ranked = sorted(self.weights.items(), key=lambda item: (-item[1], item[0]))
        return [topic for topic, _ in ranked[:count]]


@dataclass
class ReadingRecord:
    document_id: UUID
    title: str
    furthest_paragraph: int
    total_paragraphs: int
    last_read: datetime

    @property
    def completed(self) -> bool:
        return self.total_paragraphs > 0 and self.furthest_paragraph >= self.total_paragraphs

    @property
    def progress(self) -> float:
        if self.total_paragraphs <= 0:
            return 0.0
        return min(1.0, self.furthest_paragraph / self.total_paragraphs)


@dataclass
class ReadingHistory:
    records: dict[UUID, ReadingRecord] = field(default_factory=dict)

    def record(
        self,
        document_id: UUID,
        title: str,
        paragraph: int,
        total_paragraphs: int,
        when: datetime,
    ) -> ReadingRecord:
        """Note that the reader reached ``paragraph``. Progress only moves
        forward, so re-reading an earlier section keeps the furthest point."""
        existing = self.records.get(document_id)
        furthest = max(paragraph, existing.furthest_paragraph if existing else 0)
        record = ReadingRecord(document_id, title, furthest, total_paragraphs, when)
        self.records[document_id] = record
        return record

    def get(self, document_id: UUID) -> ReadingRecord | None:
        return self.records.get(document_id)

    def recent(self, count: int = 10) -> list[ReadingRecord]:
        return sorted(self.records.values(), key=lambda r: r.last_read, reverse=True)[:count]

    def completed(self) -> list[ReadingRecord]:
        return [r for r in self.records.values() if r.completed]


@dataclass
class ReaderProfile:
    knowledge: KnowledgeProfile = field(default_factory=KnowledgeProfile)
    interests: InterestProfile = field(default_factory=InterestProfile)
    history: ReadingHistory = field(default_factory=ReadingHistory)
    explanation_depth: ExplanationDepth = ExplanationDepth.STANDARD
    personalization_enabled: bool = True
    background: str = ""  # free text the reader chose to share about themselves

    @property
    def is_sparse(self) -> bool:
        """Too little is known to personalize honestly."""
        return not (self.knowledge.areas or self.interests.weights or self.history.records)
