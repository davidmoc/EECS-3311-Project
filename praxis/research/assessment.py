"""What one assessment of the developing situation found (F03, SD01).

``DialecticalMaterialistResearchMethod.assess`` produces a
``ResearchAssessment``; ``ConcreteSituationBuilder`` adds its findings to the
situation, ``ResearchStoppingPolicy`` reads whether more research is needed,
and ``ResearchPlanner.revise_plan`` turns its follow-up searches into
commands.
"""

from __future__ import annotations

from dataclasses import dataclass

from praxis.research.situation import (
    ConflictingEvidence,
    Contradiction,
    HistoricalDevelopment,
    MaterialRelation,
)

# The kinds of follow-up search an assessment may ask for.
FOLLOW_UP_KINDS = ("relation", "contradiction", "history", "evidence", "theory")


@dataclass(frozen=True)
class FollowUp:
    """A search the assessment says would fill a gap."""

    kind: str  # one of FOLLOW_UP_KINDS
    keywords: str

    def __post_init__(self) -> None:
        if self.kind not in FOLLOW_UP_KINDS:
            raise ValueError(f"Unknown follow-up kind: {self.kind!r}")


@dataclass(frozen=True)
class ResearchAssessment:
    relations: tuple[MaterialRelation, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    developments: tuple[HistoricalDevelopment, ...] = ()
    conflicting_evidence: tuple[ConflictingEvidence, ...] = ()
    follow_ups: tuple[FollowUp, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    requires_more_research: bool = False

    @property
    def missing_relations(self) -> list[str]:
        return [f.keywords for f in self.follow_ups if f.kind == "relation"]

    @property
    def historical_questions(self) -> list[str]:
        return [f.keywords for f in self.follow_ups if f.kind == "history"]

    @property
    def finding_count(self) -> int:
        return (
            len(self.relations)
            + len(self.contradictions)
            + len(self.developments)
            + len(self.conflicting_evidence)
        )

    @property
    def is_empty(self) -> bool:
        return not (self.finding_count or self.follow_ups or self.unresolved_questions)

    def summary(self) -> str:
        """What was found, for the step log, e.g. "2 contradictions, 1 relation"."""
        parts = [
            _count(len(self.contradictions), "contradiction"),
            _count(len(self.relations), "relation"),
            _count(len(self.developments), "historical development"),
            _count(len(self.conflicting_evidence), "conflict between sources",
                   "conflicts between sources"),
        ]
        return ", ".join(p for p in parts if p) or "no new findings"


def _count(n: int, singular: str, plural: str | None = None) -> str:
    if n == 0:
        return ""
    return f"{n} {singular if n == 1 else (plural or singular + 's')}"
