"""Storage for research sessions (F03, UC03 postcondition; UC15).

A research run is stored whole, as JSON: the session and its steps, the
numbered sources with their passage text, what the assessments
established, the analysis, and the plan as it stood. That is everything
needed to show the research again or continue it, even if a text it drew
on is later removed from the library.

A few columns are stored beside the JSON so the session list can be shown
without decoding every session.

Python note: ``json`` handles only dicts, lists, strings, numbers, booleans
and None, so the ``_encode_*`` and ``_decode_*`` functions convert the
dataclasses, enums, UUIDs and datetimes to and from those.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from praxis.agent.corpus import Source
from praxis.agent.response import ResponseStatus
from praxis.documents import Citation, Passage
from praxis.persistence.database import Database
from praxis.research.commands import COMMAND_KINDS, COMMAND_TYPES, ResearchCommand
from praxis.research.plan import ResearchPlan
from praxis.research.policy import StopReason
from praxis.research.result import ResearchResult
from praxis.research.session import ResearchSession, ResearchStatus, StepRecord
from praxis.research.situation import (
    ConcreteSituation,
    ConflictingEvidence,
    Contradiction,
    HistoricalDevelopment,
    MaterialRelation,
    RelationType,
)

FORMAT_VERSION = 1


@dataclass(frozen=True)
class ResearchSessionSummary:
    """One line of the session list."""

    id: UUID
    objective: str
    status: ResponseStatus
    incomplete: bool
    rounds: int
    source_count: int
    updated_at: datetime


class ResearchRepository(ABC):
    @abstractmethod
    def save(self, result: ResearchResult) -> None:
        """Store ``result``, replacing any earlier result of the same session."""

    @abstractmethod
    def get(self, session_id: UUID) -> ResearchResult | None: ...

    @abstractmethod
    def find_ids(self, prefix: str) -> list[UUID]:
        """Ids of the stored sessions whose id starts with ``prefix``."""

    @abstractmethod
    def list_recent(self, limit: int = 20) -> list[ResearchSessionSummary]:
        """The most recently updated sessions first."""


class SQLResearchRepository(ResearchRepository):
    def __init__(self, database: Database) -> None:
        self._connection = database.connection

    def save(self, result: ResearchResult) -> None:
        session = result.session
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO research_sessions VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(session.id),
                    session.objective,
                    result.status.value,
                    int(result.is_incomplete),
                    session.rounds,
                    len(result.sources),
                    result.created_at.isoformat(),
                    json.dumps(encode_result(result)),
                ),
            )

    def get(self, session_id: UUID) -> ResearchResult | None:
        row = self._connection.execute(
            "SELECT data FROM research_sessions WHERE id = ?", (str(session_id),)
        ).fetchone()
        return decode_result(json.loads(row["data"])) if row else None

    def find_ids(self, prefix: str) -> list[UUID]:
        # Ids are lowercase hex and dashes, so no LIKE wildcard can occur in
        # a valid prefix; anything else simply matches nothing.
        prefix = prefix.strip().lower()
        if not prefix or any(ch not in "0123456789abcdef-" for ch in prefix):
            return []
        rows = self._connection.execute(
            "SELECT id FROM research_sessions WHERE id LIKE ?", (prefix + "%",)
        ).fetchall()
        return [UUID(row["id"]) for row in rows]

    def list_recent(self, limit: int = 20) -> list[ResearchSessionSummary]:
        rows = self._connection.execute(
            "SELECT id, objective, status, incomplete, rounds, source_count, updated_at "
            "FROM research_sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            ResearchSessionSummary(
                UUID(row["id"]),
                row["objective"],
                ResponseStatus(row["status"]),
                bool(row["incomplete"]),
                row["rounds"],
                row["source_count"],
                datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]


# --- encoding ----------------------------------------------------------------


def _time(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _encode_command(command: ResearchCommand) -> dict[str, Any]:
    return {"kind": COMMAND_KINDS[type(command)], "query": command.query, "attempt": command.attempt}


def _decode_command(data: dict[str, Any]) -> ResearchCommand:
    return COMMAND_TYPES[data["kind"]](data["query"], data["attempt"])


def _encode_session(session: ResearchSession) -> dict[str, Any]:
    return {
        "objective": session.objective,
        "id": str(session.id),
        "status": session.status.value,
        "started_at": _time(session.started_at),
        "finished_at": _time(session.finished_at),
        "iteration_count": session.iteration_count,
        "tool_call_count": session.tool_call_count,
        "llm_call_count": session.llm_call_count,
        "tokens_used": session.tokens_used,
        "steps": [
            {
                "description": step.description,
                "succeeded": step.succeeded,
                "new_sources": list(step.new_sources),
                "error": step.error,
                "retry_of": step.retry_of,
                "is_assessment": step.is_assessment,
                "round": step.round,
            }
            for step in session.steps
        ],
        "warnings": list(session.warnings),
        "failure_reason": session.failure_reason,
        "rounds": session.rounds,
        "round_started_at": _time(session.round_started_at),
        "round_base": list(session.round_base),
        "focuses": list(session.focuses),
    }


def _decode_session(data: dict[str, Any]) -> ResearchSession:
    return ResearchSession(
        objective=data["objective"],
        id=UUID(data["id"]),
        status=ResearchStatus(data["status"]),
        started_at=_parse_time(data["started_at"]),
        finished_at=_parse_time(data["finished_at"]),
        iteration_count=data["iteration_count"],
        tool_call_count=data["tool_call_count"],
        llm_call_count=data["llm_call_count"],
        tokens_used=data["tokens_used"],
        steps=[
            StepRecord(
                step["description"],
                step["succeeded"],
                tuple(step["new_sources"]),
                step["error"],
                step["retry_of"],
                step["is_assessment"],
                step["round"],
            )
            for step in data["steps"]
        ],
        warnings=list(data["warnings"]),
        failure_reason=data["failure_reason"],
        rounds=data["rounds"],
        round_started_at=_parse_time(data["round_started_at"]),
        round_base=tuple(data["round_base"]),
        focuses=list(data["focuses"]),
    )


def _encode_source(source: Source) -> dict[str, Any]:
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


def _decode_source(data: dict[str, Any]) -> Source:
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


def _encode_situation(situation: ConcreteSituation) -> dict[str, Any]:
    return {
        "topic": situation.topic,
        "evidence": {str(n): purpose for n, purpose in situation.evidence.items()},
        "relations": [
            {"type": r.relation_type.value, "description": r.description, "evidence": list(r.evidence)}
            for r in situation.relations
        ],
        "contradictions": [
            {"pole_a": c.pole_a, "pole_b": c.pole_b, "relationship": c.relationship,
             "evidence": list(c.evidence)}
            for c in situation.contradictions
        ],
        "developments": [
            {"description": d.description, "evidence": list(d.evidence)} for d in situation.developments
        ],
        "conflicts": [
            {"description": c.description, "evidence": list(c.evidence)} for c in situation.conflicts
        ],
        "unresolved_questions": list(situation.unresolved_questions),
    }


def _decode_situation(data: dict[str, Any]) -> ConcreteSituation:
    return ConcreteSituation(
        topic=data["topic"],
        evidence={int(n): purpose for n, purpose in data["evidence"].items()},
        relations=[
            MaterialRelation(RelationType(r["type"]), r["description"], tuple(r["evidence"]))
            for r in data["relations"]
        ],
        contradictions=[
            Contradiction(c["pole_a"], c["pole_b"], c["relationship"], tuple(c["evidence"]))
            for c in data["contradictions"]
        ],
        developments=[
            HistoricalDevelopment(d["description"], tuple(d["evidence"])) for d in data["developments"]
        ],
        conflicts=[
            ConflictingEvidence(c["description"], tuple(c["evidence"])) for c in data["conflicts"]
        ],
        unresolved_questions=list(data["unresolved_questions"]),
    )


def encode_result(result: ResearchResult) -> dict[str, Any]:
    plan = result.plan
    return {
        "version": FORMAT_VERSION,
        "session": _encode_session(result.session),
        "status": result.status.value,
        "stop_reason": result.stop_reason.name if result.stop_reason else None,
        "sources": [_encode_source(source) for source in result.sources],
        "purposes": {str(n): purpose for n, purpose in result.purposes.items()},
        "summary": result.summary,
        "cited": [source.number for source in result.cited],
        "open_questions": list(result.open_questions),
        "personalized": result.personalized,
        "situation": _encode_situation(result.situation) if result.situation else None,
        "plan": None if plan is None else {
            "pending": [_encode_command(c) for c in plan.pending],
            "taken": [_encode_command(c) for c in plan.taken],
        },
        "created_at": _time(result.created_at),
    }


def decode_result(data: dict[str, Any]) -> ResearchResult:
    if data.get("version") != FORMAT_VERSION:
        raise ValueError(f"Unknown research record version {data.get('version')!r}.")
    session = _decode_session(data["session"])
    sources = tuple(_decode_source(source) for source in data["sources"])
    by_number = {source.number: source for source in sources}
    plan = data["plan"]
    return ResearchResult(
        session=session,
        status=ResponseStatus(data["status"]),
        # Stored by name, since the enum's values are sentences that may be reworded.
        stop_reason=StopReason[data["stop_reason"]] if data["stop_reason"] else None,
        sources=sources,
        purposes={int(n): purpose for n, purpose in data["purposes"].items()},
        summary=data["summary"],
        cited=tuple(by_number[n] for n in data["cited"] if n in by_number),
        open_questions=tuple(data["open_questions"]),
        personalized=data["personalized"],
        situation=_decode_situation(data["situation"]) if data["situation"] else None,
        plan=None if plan is None else ResearchPlan(
            session.objective,
            [_decode_command(c) for c in plan["pending"]],
            taken=[_decode_command(c) for c in plan["taken"]],
        ),
        created_at=_parse_time(data["created_at"]),
    )
