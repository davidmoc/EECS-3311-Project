"""ConcreteSituation, ConcreteSituationBuilder and ResearchAssessment (F03)."""

import pytest

from praxis.research import ResearchSession
from praxis.research.assessment import FollowUp, ResearchAssessment
from praxis.research.commands import CommandOutcome, ResearchContext
from praxis.research.situation import (
    ConcreteSituationBuilder,
    ConflictingEvidence,
    Contradiction,
    HistoricalDevelopment,
    MaterialRelation,
    RelationType,
)
from praxis.tools import ToolManager

builder = ConcreteSituationBuilder()


@pytest.fixture
def situation():
    """A situation holding sources 1-3."""
    situation = builder.build_initial_situation("  Why did  1848 fail? ")
    context = ResearchContext(ResearchSession("1848"), ToolManager())
    context.purposes.update({1: "history", 2: "theory", 3: "evidence"})
    builder.update_situation(situation, CommandOutcome(True, (1, 2, 3)), context)
    return situation


def test_update_records_each_new_source_with_its_purpose(situation):
    assert situation.topic == "Why did 1848 fail?"
    assert situation.evidence == {1: "history", 2: "theory", 3: "evidence"}
    assert not situation.has_findings


def test_findings_citing_retrieved_passages_are_integrated(situation):
    assessment = ResearchAssessment(
        relations=(MaterialRelation(RelationType.CLASS, "Bourgeoisie feared the workers", (1,)),),
        contradictions=(Contradiction("bourgeoisie", "monarchy", "compromised against workers", (1, 3)),),
        developments=(HistoricalDevelopment("March to the autumn counter-revolution", (3,)),),
        conflicting_evidence=(ConflictingEvidence("Who betrayed whom", (2, 3)),),
        unresolved_questions=("What did the peasants do?",),
    )

    rejected = builder.integrate_assessment(situation, assessment)

    assert rejected == 0
    assert len(situation.findings) == 4
    assert situation.contradictions[0].description == (
        "bourgeoisie vs monarchy: compromised against workers"
    )
    assert situation.unresolved_questions == ["What did the peasants do?"]


def test_findings_without_retrieved_evidence_are_left_out(situation):
    assessment = ResearchAssessment(
        relations=(
            MaterialRelation(RelationType.PRODUCTION, "uncited", ()),
            MaterialRelation(RelationType.PRODUCTION, "cites only [9]", (9,)),
            MaterialRelation(RelationType.PRODUCTION, "cites [2] and [9]", (2, 9)),
        ),
        # A disagreement needs two passages that were actually retrieved.
        conflicting_evidence=(ConflictingEvidence("one real side", (1, 9)),),
    )

    rejected = builder.integrate_assessment(situation, assessment)

    assert rejected == 3
    assert [r.description for r in situation.relations] == ["cites [2] and [9]"]
    assert situation.relations[0].evidence == (2,)  # the unknown [9] is dropped
    assert situation.conflicts == []


def test_repeated_findings_are_not_added_twice(situation):
    first = Contradiction("capital", "labour", "wages", (1,))
    again = Contradiction("Capital", "labour", "  wages", (2,))
    builder.integrate_assessment(situation, ResearchAssessment(contradictions=(first,)))

    rejected = builder.integrate_assessment(
        situation,
        ResearchAssessment(contradictions=(again,), unresolved_questions=("what next?", "What  next?")),
    )

    assert rejected == 0  # a repeat is not an unsupported claim
    assert situation.contradictions == [first]
    assert situation.unresolved_questions == ["what next?"]


def test_assessment_names_its_gaps_and_summarises_itself():
    assessment = ResearchAssessment(
        contradictions=(Contradiction("a", "b", "c", (1,)), Contradiction("d", "e", "f", (1,))),
        relations=(MaterialRelation(RelationType.CLASS, "x", (1,)),),
        follow_ups=(FollowUp("relation", "peasants landlords"), FollowUp("history", "Frankfurt assembly")),
        requires_more_research=True,
    )

    assert assessment.missing_relations == ["peasants landlords"]
    assert assessment.historical_questions == ["Frankfurt assembly"]
    assert assessment.summary() == "2 contradictions, 1 relation; 2 follow-up searches"
    assert ResearchAssessment().summary() == "no new findings; research judged sufficient"
    assert ResearchAssessment().is_empty


def test_follow_ups_must_be_a_known_kind():
    with pytest.raises(ValueError):
        FollowUp("astrology", "stars")
