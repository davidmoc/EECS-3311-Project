"""What the agent hands back to a controller."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from praxis.agent.corpus import Source


class ResponseStatus(Enum):
    ANSWERED = "answered"
    # No passage addressed the question, so no explanation was generated.
    NO_SOURCES = "no_sources"
    # Passages were found but the model could not explain them.
    EXPLANATION_FAILED = "explanation_failed"


@dataclass(frozen=True)
class AgentResponse:
    """A source-grounded answer.

    ``sources`` are the passages themselves, always shown to the reader;
    ``explanation`` is the model's commentary on them and is kept separate
    so the interface can mark it as AI-generated. ``cited`` are the sources
    the explanation actually refers to.
    """

    question: str
    status: ResponseStatus
    sources: tuple[Source, ...] = ()
    explanation: str | None = None
    cited: tuple[Source, ...] = ()
    warnings: tuple[str, ...] = ()
    personalized: bool = False
    tokens_used: int = 0
    search_terms: tuple[str, ...] = ()

    @property
    def is_grounded(self) -> bool:
        return self.status is ResponseStatus.ANSWERED and bool(self.cited)
