"""Storage for source comparisons (F10; Stage 1: "``SourceComparison``
stores the structured result").

A comparison is stored whole, as JSON, with the text of every compared
passage, so it can be shown again even if a source leaves the library.
The subject, titles and time are also columns, for the comparison list.

Import this module as ``praxis.persistence.comparisons``: it depends on
``praxis.comparison``, which depends on the agent package, and
``praxis.persistence``'s own ``__init__`` must stay importable from the
tool layer without that chain (the same reason as research storage).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from praxis.comparison import Comparability, ComparisonPoint, PointKind, SourceComparison, SourceProfile
from praxis.persistence.database import Database
from praxis.persistence.sources import decode_source, encode_source

FORMAT_VERSION = 1


@dataclass(frozen=True)
class ComparisonSummary:
    """One line of the comparison list."""

    id: UUID
    subject: str
    titles: tuple[str, ...]
    comparability: Comparability
    created_at: datetime


class ComparisonRepository(ABC):
    @abstractmethod
    def save(self, comparison: SourceComparison) -> None: ...

    @abstractmethod
    def get(self, comparison_id: UUID) -> SourceComparison | None: ...

    @abstractmethod
    def find_ids(self, prefix: str) -> list[UUID]:
        """Ids of the stored comparisons whose id starts with ``prefix``."""

    @abstractmethod
    def list_recent(self, limit: int = 20) -> list[ComparisonSummary]:
        """The newest comparisons first."""


class SQLComparisonRepository(ComparisonRepository):
    def __init__(self, database: Database) -> None:
        self._connection = database.connection

    def save(self, comparison: SourceComparison) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO comparisons VALUES (?,?,?,?,?,?)",
                (
                    str(comparison.id),
                    comparison.subject,
                    json.dumps([p.title for p in comparison.profiles]),
                    comparison.comparability.value,
                    comparison.created_at.isoformat(),
                    json.dumps(encode_comparison(comparison)),
                ),
            )

    def get(self, comparison_id: UUID) -> SourceComparison | None:
        row = self._connection.execute(
            "SELECT data FROM comparisons WHERE id = ?", (str(comparison_id),)
        ).fetchone()
        return decode_comparison(json.loads(row["data"])) if row else None

    def find_ids(self, prefix: str) -> list[UUID]:
        prefix = prefix.strip().lower()
        # Ids are hex and dashes, so a valid prefix holds no LIKE wildcard.
        if not prefix or any(ch not in "0123456789abcdef-" for ch in prefix):
            return []
        rows = self._connection.execute(
            "SELECT id FROM comparisons WHERE id LIKE ?", (prefix + "%",)
        ).fetchall()
        return [UUID(row["id"]) for row in rows]

    def list_recent(self, limit: int = 20) -> list[ComparisonSummary]:
        rows = self._connection.execute(
            "SELECT id, subject, titles, comparability, created_at FROM comparisons "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            ComparisonSummary(
                UUID(row["id"]),
                row["subject"],
                tuple(json.loads(row["titles"])),
                Comparability(row["comparability"]),
                datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]


def encode_comparison(comparison: SourceComparison) -> dict[str, Any]:
    return {
        "version": FORMAT_VERSION,
        "id": str(comparison.id),
        "subject": comparison.subject,
        "profiles": [_encode_profile(p) for p in comparison.profiles],
        "passages": [encode_source(s) for s in comparison.passages],
        "points": [
            {"kind": p.kind.value, "description": p.description,
             "evidence": list(p.evidence), "aspect": p.aspect}
            for p in comparison.points
        ],
        "comparability": comparison.comparability.value,
        "comparability_note": comparison.comparability_note,
        "uncertainties": list(comparison.uncertainties),
        "warnings": list(comparison.warnings),
        "personalized": comparison.personalized,
        "tokens_used": comparison.tokens_used,
        "created_at": comparison.created_at.isoformat(),
    }


def decode_comparison(data: dict[str, Any]) -> SourceComparison:
    if data.get("version") != FORMAT_VERSION:
        raise ValueError(f"Unknown stored comparison format {data.get('version')!r}.")
    return SourceComparison(
        id=UUID(data["id"]),
        subject=data["subject"],
        profiles=tuple(_decode_profile(p) for p in data["profiles"]),
        passages=tuple(decode_source(s) for s in data["passages"]),
        points=tuple(
            ComparisonPoint(PointKind(p["kind"]), p["description"], tuple(p["evidence"]), p["aspect"])
            for p in data["points"]
        ),
        comparability=Comparability(data["comparability"]),
        comparability_note=data["comparability_note"],
        uncertainties=tuple(data["uncertainties"]),
        warnings=tuple(data["warnings"]),
        personalized=data["personalized"],
        tokens_used=data["tokens_used"],
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def _encode_profile(profile: SourceProfile) -> dict[str, Any]:
    return {
        "document_id": str(profile.document_id),
        "title": profile.title,
        "author": profile.author,
        "kind": profile.kind,
        "outlet": profile.outlet,
        "publication_date": profile.publication_date.isoformat() if profile.publication_date else None,
        "source_url": profile.source_url,
        "license": profile.license,
    }


def _decode_profile(data: dict[str, Any]) -> SourceProfile:
    return SourceProfile(
        document_id=UUID(data["document_id"]),
        title=data["title"],
        author=data["author"],
        kind=data["kind"],
        outlet=data["outlet"],
        publication_date=date.fromisoformat(data["publication_date"]) if data["publication_date"] else None,
        source_url=data["source_url"],
        license=data["license"],
    )
