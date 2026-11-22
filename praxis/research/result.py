"""What a research run hands back to a controller (F03)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from praxis.agent.corpus import Source
from praxis.agent.response import ResponseStatus
from praxis.documents import Citation
from praxis.research.commands import ResearchCommand
from praxis.research.plan import ResearchPlan
from praxis.research.policy import StopReason
from praxis.research.session import ResearchSession, utc_now
from praxis.research.situation import ConcreteSituation


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
    # What the assessments established; None if research never got that far.
    situation: ConcreteSituation | None = None
    # The plan as research stopped: what was run, and what was still queued.
    # Kept so the research can be continued without repeating a search.
    plan: ResearchPlan | None = None
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

    @property
    def unfinished_steps(self) -> list[ResearchCommand]:
        """Planned steps that were not run because a limit was reached."""
        if self.plan is None or self.stop_reason is None or not self.stop_reason.is_budget:
            return []
        return self.plan.pending

    @property
    def is_incomplete(self) -> bool:
        """No analysis was written, or a limit cut the plan short (UC15:
        such a session is restored as incomplete, not as complete)."""
        return self.status is not ResponseStatus.ANSWERED or bool(self.unfinished_steps)

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
