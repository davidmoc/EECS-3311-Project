"""ResearchPlanner.create_initial_plan and the plan prompt (F03)."""

from conftest import ScriptedLLM

from praxis.agent import PromptBuilder
from praxis.llm import LLMError
from praxis.reader_model import KnowledgeLevel, ReaderProfile
from praxis.research import ResearchSession
from praxis.research.assessment import FollowUp, ResearchAssessment
from praxis.research.commands import (
    InvestigateContradictionCommand,
    InvestigateRelationCommand,
    RetrieveEvidenceCommand,
    RetrieveTheoryCommand,
    TraceHistoricalDevelopmentCommand,
)
from praxis.research.plan import ResearchPlan
from praxis.research.planner import FALLBACK_PLAN_WARNING, ResearchPlanner

OBJECTIVE = "Why did the German revolution of 1848 fail?"


def test_plan_follows_the_model_then_searches_the_question():
    llm = ScriptedLLM(
        "history: 1848 revolution, Germany\n"
        "evidence: bourgeoisie, monarchy, compromise\n"
        "theory: class struggle"
    )
    session = ResearchSession(OBJECTIVE)

    plan = ResearchPlanner(llm).create_initial_plan(session)

    assert plan.pending == [
        TraceHistoricalDevelopmentCommand("1848 revolution, Germany"),
        RetrieveEvidenceCommand("bourgeoisie, monarchy, compromise"),
        RetrieveTheoryCommand("class struggle"),
        RetrieveEvidenceCommand(OBJECTIVE),
    ]
    assert session.llm_call_count == 1 and session.tokens_used == 15
    assert session.warnings == []
    assert llm.prompts[0].user == OBJECTIVE


def test_unusable_reply_falls_back_to_a_basic_plan():
    session = ResearchSession(OBJECTIVE)

    plan = ResearchPlanner(ScriptedLLM("I would start by reading Marx.")).create_initial_plan(session)

    assert plan.pending == [RetrieveTheoryCommand(OBJECTIVE), RetrieveEvidenceCommand(OBJECTIVE)]
    assert session.warnings == [FALLBACK_PLAN_WARNING]


def test_model_failure_and_no_model_also_fall_back():
    failed = ResearchSession(OBJECTIVE)
    ResearchPlanner(ScriptedLLM(LLMError("timeout"))).create_initial_plan(failed)
    offline = ResearchSession(OBJECTIVE)
    plan = ResearchPlanner(None).create_initial_plan(offline)

    assert failed.warnings == [FALLBACK_PLAN_WARNING]
    assert failed.llm_call_count == 1  # the failed call still counts
    assert offline.llm_call_count == 0
    assert len(plan) == 2


def test_parse_plan_accepts_bullets_and_numbering_and_drops_the_rest():
    text = (
        "Here is the plan:\n"
        "1. Evidence: wages, subsistence.\n"
        "- THEORY: surplus value\n"
        "* history:   enclosure   of land\n"
        "theory: surplus value\n"
        "economics: prices\n"
        "evidence:   \n"
    )

    assert PromptBuilder.parse_plan(text) == [
        ("evidence", "wages, subsistence"),
        ("theory", "surplus value"),
        ("history", "enclosure of land"),
    ]


def test_parse_plan_keeps_at_most_four_steps():
    """Four planned steps plus the question leave room in the source list
    for the searches an assessment adds."""
    text = "\n".join(f"evidence: topic {n}" for n in range(9))

    assert len(PromptBuilder.parse_plan(text)) == 4


def test_plan_prompt_mentions_the_reader_only_when_known():
    profile = ReaderProfile()
    profile.knowledge.update_level("class struggle", KnowledgeLevel.INTRODUCTORY)
    builder = PromptBuilder()

    personal = builder.build_plan_prompt(OBJECTIVE, profile)
    general = builder.build_plan_prompt(OBJECTIVE, ReaderProfile())

    assert "About the reader" in personal.system
    assert "About the reader" not in general.system


# --- revise_plan ---------------------------------------------------------------


def test_revision_queues_the_assessments_follow_ups_once():
    plan = ResearchPlan(OBJECTIVE, [RetrieveEvidenceCommand("bourgeoisie")])
    plan.get_next_command()  # already run
    plan.add_command(TraceHistoricalDevelopmentCommand("Frankfurt assembly"))  # already queued
    assessment = ResearchAssessment(
        follow_ups=(
            FollowUp("relation", "peasants landlords"),
            FollowUp("evidence", "bourgeoisie"),
            FollowUp("history", "Frankfurt assembly"),
            FollowUp("contradiction", "town and country"),
        ),
        requires_more_research=True,
    )

    added = ResearchPlanner(None).revise_plan(plan, assessment)

    assert added == [
        InvestigateRelationCommand("peasants landlords"),
        InvestigateContradictionCommand("town and country"),
    ]
    assert plan.pending == [TraceHistoricalDevelopmentCommand("Frankfurt assembly"), *added]


def test_no_revision_when_the_research_is_judged_sufficient():
    plan = ResearchPlan(OBJECTIVE)
    assessment = ResearchAssessment(follow_ups=(FollowUp("theory", "value"),), requires_more_research=False)

    assert ResearchPlanner(None).revise_plan(plan, assessment) == []
    assert plan.is_complete()
