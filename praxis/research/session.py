"""The state of one research run (F03, SD01).

``ResearchSession`` counts what the run has spent; ``ResearchBudget`` says
how much it may spend. ``ResearchStoppingPolicy`` compares the two.

Python note: ``@dataclass`` writes ``__init__`` (and equality, and a
readable ``repr``) from the annotated fields, much like a Go struct literal.
``frozen=True`` makes instances immutable after construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
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
    round: int = 1  # which round of the session ran it (see ResearchSession.resume)


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
    # A session can be continued later (``resume``). Each continuation is a
    # new round with its own budget; the counters above stay cumulative and
    # ``round_base`` holds their values when the current round began.
    rounds: int = 1
    round_started_at: datetime | None = None
    round_base: tuple[int, int, int] = (0, 0, 0)  # iterations, tool calls, model calls

    def __post_init__(self) -> None:
        self.objective = " ".join(self.objective.split())
        if not self.objective:
            raise ResearchError("A research objective is required.")
        if self.round_started_at is None:
            self.round_started_at = self.started_at

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
        """Append ``step``, marked with the current round, and return its index."""
        self._require_running()
        self.steps.append(replace(step, round=self.rounds))
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

    def resume(self, at: datetime | None = None) -> None:
        """Start another round of a finished session.

        The steps, counters and sources of earlier rounds are kept; the
        budget applies to the new round only. Warnings are cleared: they
        described the previous result, which the new round replaces.
        """
        if self.is_running:
            raise ResearchError("The research session is still running.")
        at = at or utc_now()
        self.status = ResearchStatus.RUNNING
        self.finished_at = None
        self.failure_reason = None
        self.warnings.clear()
        self.rounds += 1
        self.round_started_at = at
        self.round_base = (self.iteration_count, self.tool_call_count, self.llm_call_count)

    @property
    def is_running(self) -> bool:
        return self.status is ResearchStatus.RUNNING

    @property
    def round_iteration_count(self) -> int:
        return self.iteration_count - self.round_base[0]

    @property
    def round_tool_call_count(self) -> int:
        return self.tool_call_count - self.round_base[1]

    @property
    def round_llm_call_count(self) -> int:
        return self.llm_call_count - self.round_base[2]

    def elapsed_seconds(self, now: datetime) -> float:
        return ((self.finished_at or now) - self.started_at).total_seconds()

    def round_elapsed_seconds(self, now: datetime) -> float:
        return ((self.finished_at or now) - self.round_started_at).total_seconds()

    def _require_running(self) -> None:
        if not self.is_running:
            raise ResearchError(f"The research session is already {self.status.value}.")
