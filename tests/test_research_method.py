"""DialecticalMaterialistResearchMethod and the assessment prompt (F03)."""

from conftest import ScriptedLLM

from praxis.agent import ResearchCorpus
from praxis.agent.corpus import cited_numbers
from praxis.documents import Book
from praxis.llm import LLMError
from praxis.research import ResearchSession, StepRecord
from praxis.research.assessment import FollowUp
from praxis.research.commands import ResearchContext
from praxis.research.method import (
    ASSESSMENT_UNREADABLE,
    DialecticalMaterialistResearchMethod,
    established_lines,
    parse_assessment,
)
from praxis.research.situation import (
    ConcreteSituation,
    Contradiction,
    RelationType,
)
from praxis.tools import ToolManager

REPLY = """\
relation: class | The bourgeoisie feared the proletariat more than the monarchy [1, 2]
- contradiction: bourgeoisie | monarchy | they compromised against the workers [2]
**development**: March risings gave way to counter-revolution by autumn [3].
conflict: Passages differ on who abandoned the revolution first [1, 3]
1. search: relation | peasants landlords feudal dues
search: history: Frankfurt National Assembly
search: astrology | stars
question: What role did the peasantry play?
verdict: more research needed
Some commentary the parser should ignore.
"""


def test_reply_lines_become_typed_findings_and_follow_ups():
    assessment = parse_assessment(REPLY)

    (relation,) = assessment.relations
    assert relation.relation_type is RelationType.CLASS
    assert relation.description == "The bourgeoisie feared the proletariat more than the monarchy"
    assert relation.evidence == (1, 2)
    (contradiction,) = assessment.contradictions
    assert (contradiction.pole_a, contradiction.pole_b) == ("bourgeoisie", "monarchy")
    assert contradiction.relationship == "they compromised against the workers"
    assert assessment.developments[0].evidence == (3,)
    assert assessment.conflicting_evidence[0].evidence == (1, 3)
    assert assessment.follow_ups == (
        FollowUp("relation", "peasants landlords feudal dues"),
        FollowUp("history", "Frankfurt National Assembly"),
    )
    assert assessment.unresolved_questions == ("What role did the peasantry play?",)
    assert assessment.requires_more_research


def test_verdict_decides_whether_more_research_is_needed():
    assert not parse_assessment("search: theory | value\nverdict: sufficient").requires_more_research
    # No verdict: more research is needed only if a search was proposed.
    assert parse_assessment("search: theory | value").requires_more_research
    assert not parse_assessment("development: x [1]").requires_more_research


def test_at_most_three_follow_ups_are_kept_without_repeats():
    reply = "\n".join(f"search: evidence | topic {n}" for n in (1, 1, 2, 3, 4))
    assert [f.keywords for f in parse_assessment(reply).follow_ups] == ["topic 1", "topic 2", "topic 3"]


def test_unknown_relation_types_and_malformed_lines_are_ignored():
    assessment = parse_assessment("relation: astral | planets [1]\nrelation: no type given [1]\ncontradiction: one side only [1]")
    assert assessment.is_empty


def test_a_bare_verdict_is_an_assessment_but_prose_is_not():
    bare = parse_assessment("verdict: sufficient")
    assert bare is not None and bare.is_empty and not bare.requires_more_research
    assert parse_assessment("I think the research is fine.\nNote: none") is None


def test_established_findings_are_written_back_in_the_reply_format():
    situation = ConcreteSituation("1848", evidence={1: "evidence"})
    situation.add_contradiction(Contradiction("capital", "labour", "wages", (1,)))
    assert established_lines(situation) == ["contradiction: capital | labour | wages [1]"]


def test_cited_numbers_are_unique_and_in_order():
    assert cited_numbers("a [3] b [1, 3] c [2]") == [3, 1, 2]


# --- assess() ------------------------------------------------------------------


def context_with_sources():
    session = ResearchSession("Why did 1848 fail?")
    context = ResearchContext(session, ToolManager())
    book = Book(title="Revolution", author="Engels", text="The bourgeoisie betrayed the workers of Berlin in 1848.", license="Public Domain")
    context.corpus.add_passage(book, book.passages()[0])
    context.purposes[1] = "history"
    session.record_step(StepRecord("Trace historical development: 1848", True, (1,)))
    session.record_step(StepRecord("Retrieve theory: value", False, error="down"))
    return context


def test_assess_asks_once_and_counts_the_call():
    llm = ScriptedLLM("development: Berlin rising [1]\nverdict: sufficient")
    context = context_with_sources()
    situation = ConcreteSituation("1848", evidence={1: "history"})
    situation.add_contradiction(Contradiction("a", "b", "c", (1,)))

    assessment = DialecticalMaterialistResearchMethod(llm).assess(situation, context)

    assert assessment.developments[0].description == "Berlin rising"
    assert not assessment.requires_more_research
    assert context.session.llm_call_count == 1 and context.session.tokens_used == 15
    prompt = llm.prompts[0]
    assert "verdict: <sufficient|more research needed>" in prompt.system
    assert "Searches already made:\n- Trace historical development: 1848\n" in prompt.user
    assert "Retrieve theory: value" not in prompt.user  # it failed, so it found nothing
    assert "Already established (do not repeat these):\n- contradiction: a | b | c [1]" in prompt.user
    assert "### Retrieved for historical development\n\n[1] " in prompt.user


def test_a_failed_or_unreadable_assessment_is_none_with_a_warning():
    context = context_with_sources()
    situation = ConcreteSituation("1848")

    failed = DialecticalMaterialistResearchMethod(ScriptedLLM(LLMError("timeout"))).assess(situation, context)
    unreadable = DialecticalMaterialistResearchMethod(ScriptedLLM("I think it failed.")).assess(situation, context)

    assert failed is None and unreadable is None
    assert context.session.warnings == [
        "The research could not be assessed (timeout), so the plan was not revised.",
        ASSESSMENT_UNREADABLE,
    ]
    assert context.session.llm_call_count == 2


def test_nothing_to_assess_without_a_model_or_sources():
    empty = ResearchContext(ResearchSession("x"), ToolManager(), corpus=ResearchCorpus())
    assert DialecticalMaterialistResearchMethod(None).assess(ConcreteSituation("x"), context_with_sources()) is None
    assert DialecticalMaterialistResearchMethod(ScriptedLLM()).assess(ConcreteSituation("x"), empty) is None
