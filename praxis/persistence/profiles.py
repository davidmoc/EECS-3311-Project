"""Storage for the single local reader's profile.

The profile is a small tree of objects that is always read and written as a
whole, so it is stored as one JSON document rather than spread over tables.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID

from praxis.persistence.database import Database
from praxis.reader_model import (
    AssessmentSource,
    ExplanationDepth,
    InterestProfile,
    KnowledgeArea,
    KnowledgeLevel,
    KnowledgeProfile,
    ReaderProfile,
    ReadingHistory,
    ReadingRecord,
)


class ReaderProfileRepository(ABC):
    @abstractmethod
    def load(self) -> ReaderProfile:
        """The stored profile, or a new empty one if none exists yet."""

    @abstractmethod
    def save(self, profile: ReaderProfile) -> None: ...


class SQLReaderProfileRepository(ReaderProfileRepository):
    def __init__(self, database: Database) -> None:
        self._connection = database.connection

    def load(self) -> ReaderProfile:
        row = self._connection.execute(
            "SELECT data FROM reader_profile WHERE id = 1"
        ).fetchone()
        return profile_from_dict(json.loads(row["data"])) if row else ReaderProfile()

    def save(self, profile: ReaderProfile) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO reader_profile (id, data) VALUES (1, ?)",
                (json.dumps(profile_to_dict(profile)),),
            )


def profile_to_dict(profile: ReaderProfile) -> dict[str, Any]:
    return {
        "knowledge": [
            {
                "topic": area.topic,
                "level": area.level.name,
                "source": area.source.value,
                "evidence": area.evidence,
            }
            for area in profile.knowledge.areas.values()
        ],
        "interests": profile.interests.weights,
        "dismissed_interests": sorted(profile.interests.dismissed),
        "history": [
            {
                "document_id": str(record.document_id),
                "title": record.title,
                "furthest_paragraph": record.furthest_paragraph,
                "total_paragraphs": record.total_paragraphs,
                "last_read": record.last_read.isoformat(),
            }
            for record in profile.history.records.values()
        ],
        "explanation_depth": profile.explanation_depth.value,
        "personalization_enabled": profile.personalization_enabled,
        "background": profile.background,
    }


def profile_from_dict(data: dict[str, Any]) -> ReaderProfile:
    areas = {
        item["topic"]: KnowledgeArea(
            topic=item["topic"],
            level=KnowledgeLevel[item["level"]],
            source=AssessmentSource(item["source"]),
            evidence=item.get("evidence", 0),
        )
        for item in data.get("knowledge", [])
    }
    records = {}
    for item in data.get("history", []):
        record = ReadingRecord(
            document_id=UUID(item["document_id"]),
            title=item["title"],
            furthest_paragraph=item["furthest_paragraph"],
            total_paragraphs=item["total_paragraphs"],
            last_read=datetime.fromisoformat(item["last_read"]),
        )
        records[record.document_id] = record
    return ReaderProfile(
        knowledge=KnowledgeProfile(areas),
        interests=InterestProfile(
            dict(data.get("interests", {})), set(data.get("dismissed_interests", []))
        ),
        history=ReadingHistory(records),
        explanation_depth=ExplanationDepth(data.get("explanation_depth", "standard")),
        personalization_enabled=data.get("personalization_enabled", True),
        background=data.get("background", ""),
    )
