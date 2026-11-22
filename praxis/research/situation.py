"""The agent's structured understanding of what it is researching (F03, SD01).

``ConcreteSituation`` collects the evidence gathered so far and what has
been established from it: material relations, contradictions, historical
developments, and places where the sources disagree. Every finding names
the numbered sources it rests on, so the synthesis and the reader can check
it against the passages.

``ConcreteSituationBuilder`` is the only thing that changes a situation. It
refuses findings that cite no retrieved passage, so an interpretation the
model produced from memory never becomes part of the situation.

Python note: findings are frozen dataclasses holding tuples. A tuple is an
immutable list, so a finding cannot change after it has been checked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:  # imported only for type checkers, avoiding an import cycle
    from praxis.research.assessment import ResearchAssessment
    from praxis.research.commands import CommandOutcome, ResearchContext


class RelationType(Enum):
    CLASS = "class"
    PRODUCTION = "production"
    INSTITUTIONAL = "institutional"
    IDEOLOGICAL = "ideological"


@dataclass(frozen=True)
class MaterialRelation:
    """How classes, production, institutions or ideas bear on each other."""

    relation_type: RelationType
    description: str
    evidence: tuple[int, ...] = ()  # source numbers

    def with_evidence(self, evidence: tuple[int, ...]) -> MaterialRelation:
        return MaterialRelation(self.relation_type, self.description, evidence)


@dataclass(frozen=True)
class Contradiction:
    """Two sides of a tension internal to the situation, and how they relate."""

    pole_a: str
    pole_b: str
    relationship: str
    evidence: tuple[int, ...] = ()

    @property
    def description(self) -> str:
        return f"{self.pole_a} vs {self.pole_b}: {self.relationship}"

    def with_evidence(self, evidence: tuple[int, ...]) -> Contradiction:
        return Contradiction(self.pole_a, self.pole_b, self.relationship, evidence)


@dataclass(frozen=True)
class HistoricalDevelopment:
    """How the situation or its conditions changed over time."""

    description: str
    evidence: tuple[int, ...] = ()

    def with_evidence(self, evidence: tuple[int, ...]) -> HistoricalDevelopment:
        return HistoricalDevelopment(self.description, evidence)


@dataclass(frozen=True)
class ConflictingEvidence:
    """Passages that disagree. Recorded, not resolved by dropping one side."""

    description: str
    evidence: tuple[int, ...] = ()

    def with_evidence(self, evidence: tuple[int, ...]) -> ConflictingEvidence:
        return ConflictingEvidence(self.description, evidence)


Finding = Union[MaterialRelation, Contradiction, HistoricalDevelopment, ConflictingEvidence]


@dataclass
class ConcreteSituation:
    topic: str
    # Source number -> why it was retrieved ("evidence", "theory", ...).
    evidence: dict[int, str] = field(default_factory=dict)
    relations: list[MaterialRelation] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    developments: list[HistoricalDevelopment] = field(default_factory=list)
    conflicts: list[ConflictingEvidence] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)

    def add_evidence(self, number: int, purpose: str) -> None:
        self.evidence.setdefault(number, purpose)

    def has_evidence(self, number: int) -> bool:
        return number in self.evidence

    def add_relation(self, relation: MaterialRelation) -> bool:
        return _add_new(self.relations, relation)

    def add_contradiction(self, contradiction: Contradiction) -> bool:
        return _add_new(self.contradictions, contradiction)

    def add_historical_development(self, development: HistoricalDevelopment) -> bool:
        return _add_new(self.developments, development)

    def add_conflict(self, conflict: ConflictingEvidence) -> bool:
        return _add_new(self.conflicts, conflict)

    def add_unresolved_question(self, question: str) -> bool:
        question = " ".join(question.split())
        if not question or _key(question) in {_key(q) for q in self.unresolved_questions}:
            return False
        self.unresolved_questions.append(question)
        return True

    @property
    def findings(self) -> list[Finding]:
        return [*self.relations, *self.contradictions, *self.developments, *self.conflicts]

    @property
    def has_findings(self) -> bool:
        return bool(self.findings)


def _key(text: str) -> str:
    return " ".join(text.casefold().split())


def _add_new(findings: list, finding: Finding) -> bool:
    """Append ``finding`` unless one with the same description is there."""
    if _key(finding.description) in {_key(f.description) for f in findings}:
        return False
    findings.append(finding)
    return True


class ConcreteSituationBuilder:
    def build_initial_situation(self, topic: str) -> ConcreteSituation:
        return ConcreteSituation(" ".join(topic.split()))

    def update_situation(
        self,
        situation: ConcreteSituation,
        outcome: CommandOutcome,
        context: ResearchContext,
    ) -> None:
        """Add the sources a research command just retrieved."""
        for number in outcome.new_sources:
            situation.add_evidence(number, context.purposes.get(number, "evidence"))

    def integrate_assessment(
        self, situation: ConcreteSituation, assessment: ResearchAssessment
    ) -> int:
        """Add the assessment's findings and open questions to ``situation``.

        Returns how many findings were left out because they cite no
        retrieved passage.
        """
        integrations = [
            (assessment.relations, self.integrate_relation),
            (assessment.contradictions, self.integrate_contradiction),
            (assessment.developments, self.integrate_historical_development),
            (assessment.conflicting_evidence, self.integrate_conflict),
        ]
        rejected = 0
        for findings, integrate in integrations:
            for finding in findings:
                if _grounded(situation, finding) is None:
                    rejected += 1
                else:
                    integrate(situation, finding)
        for question in assessment.unresolved_questions:
            situation.add_unresolved_question(question)
        return rejected

    # Each integrate_* returns True if the finding was added: it cites at
    # least one retrieved passage (two for conflicts) and is not a repeat.
    # References to passages that were not retrieved are dropped.

    def integrate_relation(self, situation: ConcreteSituation, relation: MaterialRelation) -> bool:
        grounded = _grounded(situation, relation)
        return grounded is not None and situation.add_relation(grounded)

    def integrate_contradiction(
        self, situation: ConcreteSituation, contradiction: Contradiction
    ) -> bool:
        grounded = _grounded(situation, contradiction)
        return grounded is not None and situation.add_contradiction(grounded)

    def integrate_historical_development(
        self, situation: ConcreteSituation, development: HistoricalDevelopment
    ) -> bool:
        grounded = _grounded(situation, development)
        return grounded is not None and situation.add_historical_development(grounded)

    def integrate_conflict(
        self, situation: ConcreteSituation, conflict: ConflictingEvidence
    ) -> bool:
        grounded = _grounded(situation, conflict)
        return grounded is not None and situation.add_conflict(grounded)


def _grounded(situation: ConcreteSituation, finding: Finding):
    """``finding`` citing only retrieved passages, or None if too few remain.

    A disagreement needs at least two passages; any other finding one.
    """
    minimum = 2 if isinstance(finding, ConflictingEvidence) else 1
    known = tuple(dict.fromkeys(n for n in finding.evidence if situation.has_evidence(n)))
    if len(known) < minimum:
        return None
    return finding.with_evidence(known)
