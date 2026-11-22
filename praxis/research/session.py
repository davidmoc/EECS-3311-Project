"""The state of one research run (F03, SD01).

``ResearchSession`` counts what the run has spent; ``ResearchBudget`` says
how much it may spend. ``ResearchStoppingPolicy`` compares the two.

Python note: ``@dataclass`` writes ``__init__`` (and equality, and a
readable ``repr``) from the annotated fields, much like a Go struct literal.
``frozen=True`` makes instances immutable after construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchError(Exception):
    """A research request or session operation was invalid."""


class ResearchStatus(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ResearchBudget:
    """Upper limits on one research run. Reaching any of them stops it."""

    max_iterations: int = 10
    max_tool_calls: int = 14
    max_duration_seconds: float = 240.0
    max_llm_calls: int = 4

    def __post_init__(self) -> None:
        for name in ("max_iterations", "max_tool_calls", "max_duration_seconds", "max_llm_calls"):
            if getattr(self, name) <= 0:
                raise ResearchError(f"{name} must be positive.")


@dataclass(frozen=True)
class StepRecord:
    """What one executed research command did, for the reader to inspect."""

    description: str
    succeeded: bool
    new_sources: tuple[int, ...] = ()  # source numbers this step added
    error: str | None = None
    retry_of: int | None = None  # index of the step this one retried
    is_assessment: bool = False  # an assessment of the situation, not a search


@dataclass
class ResearchSession:
    objective: str
    id: UUID = field(default_factory=uuid4)
    status: ResearchStatus = ResearchStatus.RUNNING
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    iteration_count: int = 0
    tool_call_count: int = 0
    llm_call_count: int = 0
    tokens_used: int = 0
    steps: list[StepRecord] = field(default_factory=list)
    # Things the reader should know about how the run went.
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        self.objective = " ".join(self.objective.split())
        if not self.objective:
            raise ResearchError("A research objective is required.")

    def increment_iteration(self) -> None:
        self._require_running()
        self.iteration_count += 1

    def increment_tool_calls(self) -> None:
        self._require_running()
        self.tool_call_count += 1

    def increment_llm_calls(self, tokens: int = 0) -> None:
        self._require_running()
        self.llm_call_count += 1
        self.tokens_used += tokens

    def add_warning(self, warning: str) -> None:
        if warning not in self.warnings:
            self.warnings.append(warning)

    def record_step(self, step: StepRecord) -> int:
        """Append ``step`` and return its index."""
        self._require_running()
        self.steps.append(step)
        return len(self.steps) - 1

    def complete(self, at: datetime | None = None) -> None:
        self._require_running()
        self.status = ResearchStatus.COMPLETED
        self.finished_at = at or utc_now()

    def fail(self, reason: str, at: datetime | None = None) -> None:
        self._require_running()
        self.status = ResearchStatus.FAILED
        self.failure_reason = reason
        self.finished_at = at or utc_now()

    @property
    def is_running(self) -> bool:
        return self.status is ResearchStatus.RUNNING

    def elapsed_seconds(self, now: datetime) -> float:
        return ((self.finished_at or now) - self.started_at).total_seconds()

    def _require_running(self) -> None:
        if not self.is_running:
            raise ResearchError(f"The research session is already {self.status.value}.")
