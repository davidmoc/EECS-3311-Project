"""Storage for learning paths (F08; UC08: "progress can be retained").

A path is stored whole, as JSON, with the text of every reading, so it can
be shown again even if a text leaves the library. The target, counts and
times are also columns, for the path list.

Import this module as ``praxis.persistence.learning_paths``: it depends on
``praxis.reading``, which depends on the tool layer, and the tool layer
imports ``praxis.persistence`` (the same reason as research storage).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from praxis.persistence.citations import decode_citation, encode_citation
from praxis.persistence.database import Database
from praxis.reading.prerequisites import LearningPath, LearningStep, Prerequisite, StepStatus

FORMAT_VERSION = 1


@dataclass(frozen=True)
class LearningPathSummary:
    """One line of the path list."""

    id: UUID
    target: str
    step_count: int
    settled_count: int  # steps done, already known or skipped
    created_at: datetime
    updated_at: datetime


class LearningPathRepository(ABC):
    @abstractmethod
    def save(self, path: LearningPath) -> None: ...

    @abstractmethod
    def get(self, path_id: UUID) -> LearningPath | None: ...

    @abstractmethod
    def find_ids(self, prefix: str) -> list[UUID]:
        """Ids of the stored paths whose id starts with ``prefix``."""

    @abstractmethod
    def list_recent(self, limit: int = 20) -> list[LearningPathSummary]:
        """The most recently changed paths first."""


class SQLLearningPathRepository(LearningPathRepository):
    def __init__(self, database: Database, clock=lambda: datetime.now(timezone.utc)) -> None:
        self._connection = database.connection
        self._clock = clock

    def save(self, path: LearningPath) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO learning_paths VALUES (?,?,?,?,?,?,?)",
                (
                    str(path.id),
                    path.target,
                    len(path.steps),
                    path.settled_count,
                    path.created_at.isoformat(),
                    self._clock().isoformat(),
                    json.dumps(encode_path(path)),
                ),
            )

    def get(self, path_id: UUID) -> LearningPath | None:
        row = self._connection.execute(
            "SELECT data FROM learning_paths WHERE id = ?", (str(path_id),)
        ).fetchone()
        return decode_path(json.loads(row["data"])) if row else None

    def find_ids(self, prefix: str) -> list[UUID]:
        prefix = prefix.strip().lower()
        # Ids are hex and dashes, so a valid prefix holds no LIKE wildcard.
        if not prefix or any(ch not in "0123456789abcdef-" for ch in prefix):
            return []
        rows = self._connection.execute(
            "SELECT id FROM learning_paths WHERE id LIKE ?", (prefix + "%",)
        ).fetchall()
        return [UUID(row["id"]) for row in rows]

    def list_recent(self, limit: int = 20) -> list[LearningPathSummary]:
        rows = self._connection.execute(
            "SELECT id, target, step_count, settled_count, created_at, updated_at "
            "FROM learning_paths ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            LearningPathSummary(
                UUID(row["id"]),
                row["target"],
                row["step_count"],
                row["settled_count"],
                datetime.fromisoformat(row["created_at"]),
                datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]


def encode_path(path: LearningPath) -> dict[str, Any]:
    return {
        "version": FORMAT_VERSION,
        "id": str(path.id),
        "target": path.target,
        "steps": [_encode_step(step) for step in path.steps],
        "already_known": list(path.already_known),
        "personalized": path.personalized,
        "target_document_id": str(path.target_document_id) if path.target_document_id else None,
        "warnings": list(path.warnings),
        "tokens_used": path.tokens_used,
        "created_at": path.created_at.isoformat(),
    }


def decode_path(data: dict[str, Any]) -> LearningPath:
    if data.get("version") != FORMAT_VERSION:
        raise ValueError(f"Unknown stored learning path format {data.get('version')!r}.")
    return LearningPath(
        id=UUID(data["id"]),
        target=data["target"],
        steps=[_decode_step(step) for step in data["steps"]],
        already_known=tuple(data["already_known"]),
        personalized=data["personalized"],
        target_document_id=UUID(data["target_document_id"]) if data["target_document_id"] else None,
        warnings=tuple(data["warnings"]),
        tokens_used=data["tokens_used"],
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def _encode_step(step: LearningStep) -> dict[str, Any]:
    p = step.prerequisite
    return {
        "prerequisite": {
            "name": p.name, "kind": p.kind, "essential": p.essential,
            "search": p.search, "why": p.why, "orientation": p.orientation,
        },
        "readings": [encode_citation(c) for c in step.readings],
        "required": step.required,
        "note": step.note,
        "status": step.status.value,
    }


def _decode_step(data: dict[str, Any]) -> LearningStep:
    return LearningStep(
        Prerequisite(**data["prerequisite"]),
        readings=tuple(decode_citation(c) for c in data["readings"]),
        required=data["required"],
        note=data["note"],
        status=StepStatus(data["status"]),
    )
