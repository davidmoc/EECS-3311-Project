"""PoliticalResearchAgent.analyze and analyze_research (F11, UC11)."""

import pytest
from conftest import ScriptedLLM

from praxis.agent import AgentError, PoliticalResearchAgent
from praxis.agent.agent import (
    NO_ANALYSIS_SOURCES,
    NO_LLM_WARNING,
    NO_THEORY_FOUND,
    TENTATIVE_ANALYSIS,
)
from praxis.llm import LLMError
from praxis.persistence import SQLDocumentRepository, SQLReaderProfileRepository
from praxis.persistence.research import SQLResearchRepository
from praxis.reader_model.service import ReaderProfileService
from praxis.research.analysis import AnalysisItemKind, AnalysisStatus
from praxis.tools import PassageSearchTool, ToolManager


def make_agent(database, llm):
    tools = ToolManager()
    tools.register_tool(PassageSearchTool(SQLDocumentRepository(database)))
    return PoliticalResearchAgent(
        tools, ReaderProfileService(SQLReaderProfileRepository(database)), llm,
        research_repository=SQLResearchRepository(database),
    )


# Evidence: the keyword "barricades" finds the Revolution text's ¶2 as [1];
# the issue "1848" finds its ¶1 as [2]. Theory: the concept's keywords
# find the Manifesto's ¶1 ("class struggles") as [3].
KEYWORDS = "barricades"
CONCEPTS = "concept: class struggle | freeman slave patrician | Classes fought in 1848."
ANALYSIS = """\
condition: class | Workers fought on the barricades while the liberals held back [1].
application: class struggle | The Manifesto's history of class struggles frames the barricades [3, 1].
claim: supported | The bourgeoisie chose peace with the monarchy over the workers [2, 1].
alternative: The peace may reflect military weakness rather than class fear [2].
limit: The passages say nothing about the peasantry.
"""


def test_analysis_gathers_evidence_then_theory_and_connects_them(library_database):
    llm = ScriptedLLM(KEYWORDS, CONCEPTS, ANALYSIS)
    analysis = make_agent(library_database, llm).analyze("1848", framework="historical materialism")

    assert analysis.status is AnalysisStatus.ANALYSED
    assert analysis.purposes == {1: "evidence", 2: "evidence", 3: "theory"}
    assert [c.name for c in analysis.concepts] == ["class struggle"]
    application = analysis.of_kind(AnalysisItemKind.APPLICATION)[0]
    assert (application.label, application.evidence) == ("class struggle", (3, 1))
    assert analysis.limits == ("The passages say nothing about the peasantry.",)
    assert not analysis.is_tentative
    assert [r.title for r in analysis.readings] == ["The Communist Manifesto"]
    assert analysis.tokens_used == 45
    assert "framework: historical materialism" in llm.prompts[1].user
    assert "framework: historical materialism" in llm.prompts[2].user
    assert "Retrieved for theoretical background" in llm.prompts[2].user


def test_only_tentative_claims_make_the_analysis_tentative(library_database):
    reply = ANALYSIS.replace("claim: supported |", "claim: tentative |")
    analysis = make_agent(library_database, ScriptedLLM(KEYWORDS, CONCEPTS, reply)).analyze("1848")

    assert analysis.is_tentative
    assert analysis.warnings[0] == TENTATIVE_ANALYSIS


def test_an_application_without_theory_is_left_out(library_database):
    reply = ANALYSIS.replace("[3, 1]", "[1]")
    analysis = make_agent(library_database, ScriptedLLM(KEYWORDS, CONCEPTS, reply)).analyze("1848")

    assert analysis.of_kind(AnalysisItemKind.APPLICATION) == []
    assert any("an application needs theory and evidence" in w for w in analysis.warnings)


def test_no_evidence_means_no_analysis(library_database):
    llm = ScriptedLLM("xylophone")
    analysis = make_agent(library_database, llm).analyze("xylophone")

    assert analysis.status is AnalysisStatus.NO_SOURCES
    assert NO_ANALYSIS_SOURCES in analysis.warnings
    assert len(llm.prompts) == 1


def test_without_a_model_the_evidence_is_still_returned(library_database):
    analysis = make_agent(library_database, None).analyze("1848")

    assert analysis.status is AnalysisStatus.NOT_ANALYSED
    assert len(analysis.sources) == 1
    assert NO_LLM_WARNING in analysis.warnings


def test_unusable_concepts_fall_back_to_the_framework_as_typed(library_database):
    llm = ScriptedLLM(KEYWORDS, LLMError("timeout"), ANALYSIS)
    analysis = make_agent(library_database, llm).analyze("1848", framework="class struggle")

    assert [c.name for c in analysis.concepts] == ["class struggle"]
    assert any("searched for the framework as typed" in w for w in analysis.warnings)
    assert analysis.status is AnalysisStatus.ANALYSED


def test_no_theory_means_no_analysis(library_database):
    llm = ScriptedLLM(KEYWORDS, "concept: rent | ground rent landlord | Land.")
    analysis = make_agent(library_database, llm).analyze("1848")

    assert analysis.status is AnalysisStatus.NO_THEORY
    assert NO_THEORY_FOUND in analysis.warnings
    assert len(llm.prompts) == 2


def test_an_unreadable_analysis_keeps_the_passages(library_database):
    analysis = make_agent(library_database, ScriptedLLM(KEYWORDS, CONCEPTS, "It was class fear.")).analyze("1848")

    assert analysis.status is AnalysisStatus.NOT_ANALYSED
    assert len(analysis.sources) == 3


def test_analysis_of_a_research_session_reuses_its_sources_and_findings(library_database):
    research = make_agent(library_database, ScriptedLLM(
        "evidence: barricades",
        "relation: class | Workers fought while the liberals held back [1]\nverdict: sufficient",
        "## Findings\nThe workers fought [1].",
    )).research("Why did the bourgeoisie fear the workers in 1848?")
    llm = ScriptedLLM(CONCEPTS, ANALYSIS)

    analysis = make_agent(library_database, llm).analyze_research(research.session.id)

    assert analysis.issue == "Why did the bourgeoisie fear the workers in 1848?"
    assert analysis.research_session == str(research.session.id)[:8]
    assert len(llm.prompts) == 2  # no evidence search: concepts, then the analysis
    assert "- relation: class | Workers fought while the liberals held back [1]" in llm.prompts[1].user
    assert [s.number for s in analysis.sources][: len(research.sources)] == [s.number for s in research.sources]
    assert analysis.purposes[len(research.sources) + 1] == "theory"


def test_an_empty_issue_is_refused(library_database):
    with pytest.raises(AgentError):
        make_agent(library_database, None).analyze("  ")
