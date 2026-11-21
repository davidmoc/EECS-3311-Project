"""What a research run hands back to a controller (F03)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from praxis.agent.corpus import Source
from praxis.agent.response import ResponseStatus
from praxis.documents import Citation
from praxis.research.policy import StopReason
from praxis.research.session import ResearchSession, utc_now


@dataclass(frozen=True)
class Reading:
    """A text the research drew on, suggested for further reading."""

    document_id: UUID
    title: str
    author: str


@dataclass(frozen=True)
class ResearchResult:
    """A source-grounded research result.

    As with ``AgentResponse``, the sources and the model's ``summary`` are
    kept apart so the interface can mark the summary as AI-generated.
    ``session`` holds the steps taken, what was spent, and the warnings.
    """

    session: ResearchSession
    status: ResponseStatus
    stop_reason: StopReason | None
    sources: tuple[Source, ...] = ()
    # Source number -> why it was retrieved ("evidence", "theory", "history").
    purposes: dict[int, str] = field(default_factory=dict)
    summary: str | None = None
    cited: tuple[Source, ...] = ()
    open_questions: tuple[str, ...] = ()
    personalized: bool = False
    created_at: datetime = field(default_factory=utc_now)

    @property
    def objective(self) -> str:
        return self.session.objective

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self.session.warnings)

    @property
    def is_grounded(self) -> bool:
        return self.status is ResponseStatus.ANSWERED and bool(self.cited)

    def get_citations(self) -> list[Citation]:
        return [source.citation for source in self.cited]

    def get_recommended_readings(self) -> list[Reading]:
        """The texts behind the cited sources, or behind all sources when
        nothing was cited, each once, in order of first use."""
        readings: dict[UUID, Reading] = {}
        for source in self.cited or self.sources:
            citation = source.citation
            readings.setdefault(
                citation.document_id,
                Reading(citation.document_id, citation.document_title, citation.author),
            )
        return list(readings.values())
