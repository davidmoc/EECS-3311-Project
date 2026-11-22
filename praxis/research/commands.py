"""Research commands (Command pattern, F03).

Each research action is an object with ``execute(context)``, so the planner
can create, queue, reorder and retry actions without the agent knowing
what each one does. Adding a new kind of action means adding a class here,
not another branch in the agent.

Python notes: ``ABC`` plus ``@abstractmethod`` is how Python declares an
interface; a subclass that does not implement every abstract method cannot
be instantiated. ``ClassVar`` marks a value shared by the class rather than
stored per instance.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from praxis.agent.corpus import ResearchCorpus
from praxis.reader_model import ReaderProfile
from praxis.research.session import ResearchError, ResearchSession
from praxis.tools import ToolManager, ToolResult

PASSAGE_SEARCH = "passage_search"
PASSAGES_PER_STEP = 4
MAX_SOURCES = 12
MAX_ATTEMPTS = 2


@dataclass
class ResearchContext:
    """Everything a command may read or change while it runs.

    Commands reach tools only through ``run_tool`` so that every call is
    counted against the session's budget.
    """

    session: ResearchSession
    tools: ToolManager
    corpus: ResearchCorpus = field(default_factory=ResearchCorpus)
    profile: ReaderProfile | None = None
    max_sources: int = MAX_SOURCES
    # Source number -> why it was retrieved ("evidence", "theory", "history").
    purposes: dict[int, str] = field(default_factory=dict)

    def run_tool(self, name: str, tool_input: dict[str, Any]) -> ToolResult:
        self.session.increment_tool_calls()
        return self.tools.execute_tool(name, tool_input)

    @property
    def corpus_full(self) -> bool:
        return len(self.corpus) >= self.max_sources


@dataclass(frozen=True)
class CommandOutcome:
    succeeded: bool
    new_sources: tuple[int, ...] = ()
    error: str | None = None


class ResearchCommand(ABC):
    def __init__(self, query: str, attempt: int = 1) -> None:
        query = " ".join(query.split())
        if not query:
            raise ResearchError("A research command needs a query.")
        if attempt < 1:
            raise ResearchError("Attempts are counted from 1.")
        self.query = query
        self.attempt = attempt

    @abstractmethod
    def describe(self) -> str:
        """One line saying what this command does, for the step log."""

    @abstractmethod
    def execute(self, context: ResearchContext) -> CommandOutcome: ...

    @property
    def can_retry(self) -> bool:
        return self.attempt < MAX_ATTEMPTS

    def retry(self) -> ResearchCommand:
        """The same action again, as its next attempt."""
        if not self.can_retry:
            raise ResearchError(f"'{self.describe()}' has no attempts left.")
        return type(self)(self.query, self.attempt + 1)

    @property
    def key(self) -> tuple[type, str]:
        """What makes two commands the same action, whatever the attempt
        or letter case."""
        return (type(self), self.query.casefold())

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is type(self)
            and other.query == self.query  # type: ignore[attr-defined]
            and other.attempt == self.attempt  # type: ignore[attr-defined]
        )

    def __hash__(self) -> int:
        return hash((type(self), self.query, self.attempt))

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.query!r}, attempt={self.attempt})"


class _PassageRetrievalCommand(ResearchCommand):
    """Shared behaviour of commands that pull passages from the library.

    Subclasses differ in *why* they retrieve: the purpose is recorded with
    each source, and the synthesis prompt groups sources by it.
    """

    purpose: ClassVar[str]
    label: ClassVar[str]

    def describe(self) -> str:
        return f"{self.label}: {self.query}"

    def execute(self, context: ResearchContext) -> CommandOutcome:
        if context.corpus_full:
            return CommandOutcome(True)
        result = context.run_tool(
            PASSAGE_SEARCH, {"query": self.query, "limit": PASSAGES_PER_STEP}
        )
        if not result.success:
            return CommandOutcome(False, error=result.error)
        new: list[int] = []
        for match in result.items:
            if context.corpus_full:
                break
            before = len(context.corpus)
            source = context.corpus.add_passage(match.document, match.passage)
            if len(context.corpus) > before:
                new.append(source.number)
                context.purposes[source.number] = self.purpose
        return CommandOutcome(True, tuple(new))


class RetrieveEvidenceCommand(_PassageRetrievalCommand):
    """Find passages that bear directly on the research question."""

    purpose = "evidence"
    label = "Retrieve evidence"


class RetrieveTheoryCommand(_PassageRetrievalCommand):
    """Find theoretical writing on the concepts the question involves."""

    purpose = "theory"
    label = "Retrieve theory"


class TraceHistoricalDevelopmentCommand(_PassageRetrievalCommand):
    """Find material on how the situation developed historically."""

    purpose = "history"
    label = "Trace historical development"


class InvestigateRelationCommand(_PassageRetrievalCommand):
    """Find material on a class, production, institutional or ideological
    relation the assessment found missing."""

    purpose = "relation"
    label = "Investigate relation"


class InvestigateContradictionCommand(_PassageRetrievalCommand):
    """Find material on a contradiction the assessment wants developed."""

    purpose = "contradiction"
    label = "Investigate contradiction"


# Plan-line and follow-up kinds -> the command that carries them out.
COMMAND_TYPES: dict[str, type[ResearchCommand]] = {
    "evidence": RetrieveEvidenceCommand,
    "theory": RetrieveTheoryCommand,
    "history": TraceHistoricalDevelopmentCommand,
    "relation": InvestigateRelationCommand,
    "contradiction": InvestigateContradictionCommand,
}
