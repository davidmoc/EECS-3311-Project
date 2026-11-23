"""IdeologicalContextService.compare_traditions (F12, UC12)."""

import pytest
from conftest import ScriptedLLM

from praxis.documents import Book
from praxis.library import LibraryService
from praxis.llm import LLMError
from praxis.persistence import SQLDocumentRepository, SQLReaderProfileRepository
from praxis.reader_model import KnowledgeLevel
from praxis.reader_model.service import ReaderProfileService
from praxis.reading.traditions import (
    COMPARISON_UNREADABLE,
    DESCRIBED_BY_OTHERS,
    NO_DISAGREEMENT,
    NO_LLM_ERROR,
    NO_OTHER_TRADITION,
    ONLY_ONE_PERSPECTIVE,
    IdeologicalContextService,
    StatementKind,
    TraditionsError,
    TraditionsStatus,
)
from praxis.tools import PassageSearchTool, SourceRetrievalTool, ToolManager

KROPOTKIN = (
    "The state must be abolished at once, and the people must take the bread "
    "and houses in common.\n\n"
    "The bourgeoisie will defend its state, but the workers need no new "
    "government over them."
)


@pytest.fixture
def database(library_database):
    SQLDocumentRepository(library_database).save(Book(
        title="The Conquest of Bread", author="Peter Kropotkin", text=KROPOTKIN,
        license="Public Domain",
    ))
    return library_database


def make_service(database, llm):
    documents = SQLDocumentRepository(database)
    tools = ToolManager()
    tools.register_tool(PassageSearchTool(documents))
    tools.register_tool(SourceRetrievalTool(documents))
    return IdeologicalContextService(tools, LibraryService(documents), llm)


# Marxism's search finds the Manifesto's ¶3 (the state as a committee) as
# [1]; anarchism's finds both Kropotkin paragraphs, [2] and [3].
TRADITIONS = (
    "perspective: Marxism | Karl Marx, Friedrich Engels | executive committee | The platform's own.\n"
    "perspective: Anarchism | Peter Kropotkin | abolished government | Rejects any state."
)
COMPARISON = """\
position: Marxism | The state is the instrument of the ruling class [1].
position: Anarchism | The state must be abolished at once [3].
conditions: Anarchism | Grew among those who expected no good from any government [2].
disagreement: Whether the workers need a state of their own after the revolution [1, 2].
assessment: Anarchism | Marxists hold that abolishing the state at once ignores class rule [1, 3].
gap: The passages say nothing about the Paris Commune.
"""


def test_traditions_are_compared_from_their_own_passages(database):
    llm = ScriptedLLM(TRADITIONS, COMPARISON)
    result = make_service(database, llm).compare_traditions("the state")

    assert result.status is TraditionsStatus.COMPARED
    marxism, anarchism = result.perspectives
    assert (marxism.name, marxism.own, marxism.reported) == ("Marxism", (1,), ())
    assert (anarchism.name, anarchism.own) == ("Anarchism", (2, 3))
    positions = result.statements_of("Anarchism", StatementKind.POSITION)
    assert [(p.text, p.in_own_words) for p in positions] == [
        ("The state must be abolished at once.", True),
    ]
    assert [d.evidence for d in result.disagreements] == [(1, 2)]
    assert result.statements_of("Anarchism", StatementKind.ASSESSMENT)[0].evidence == (1, 3)
    assert result.gaps == ("The passages say nothing about the Paris Commune.",)
    assert [r.title for r in anarchism.readings] == ["The Conquest of Bread"]
    assert [r.title for r in marxism.readings] == ["The Communist Manifesto"]
    assert result.warnings == ()
    assert result.tokens_used == 30
    # The model is shown each author with their titles, and the passages
    # grouped by tradition.
    assert "- Peter Kropotkin: The Conquest of Bread" in llm.prompts[0].user
    assert "## Anarchism\n\n### In its own words" in llm.prompts[1].user


def test_no_other_tradition_is_introduced_for_balance(database):
    llm = ScriptedLLM(
        "perspective: Marxism | Karl Marx | executive committee | Central.\n"
        "none: No other tradition disputes this account of 1848."
    )
    result = make_service(database, llm).compare_traditions("the state")

    assert result.status is TraditionsStatus.NO_OTHER_TRADITION
    assert result.none_reason == "No other tradition disputes this account of 1848."
    assert result.warnings[0] == NO_OTHER_TRADITION
    assert len(llm.prompts) == 1


def test_a_tradition_with_no_material_is_left_out(database):
    llm = ScriptedLLM(
        "perspective: Marxism | Karl Marx | executive committee | Central.\n"
        "perspective: Fabianism | none | xylophone | Gradual reform."
    )
    result = make_service(database, llm).compare_traditions("the state")

    assert result.status is TraditionsStatus.ONE_PERSPECTIVE
    assert result.left_out == ("Fabianism",)
    assert "No passage on this topic was found for Fabianism, so it is left out." in result.warnings
    assert ONLY_ONE_PERSPECTIVE in result.warnings
    assert len(llm.prompts) == 1


def test_a_tradition_with_no_text_of_its_own_is_described_by_others(database):
    # The library has no syndicalist author; Kropotkin's passages on the
    # workers and government are found for it, as others' description.
    llm = ScriptedLLM(
        "perspective: Marxism | Karl Marx | executive committee | Central.\n"
        "perspective: Syndicalism | none | workers government | Unions, not parties.",
        "position: Syndicalism | The workers need no government [2].\n"
        "disagreement: The state [1, 2].",
    )
    result = make_service(database, llm).compare_traditions("the state")

    syndicalism = result.perspectives[1]
    assert syndicalism.own == () and syndicalism.reported
    assert DESCRIBED_BY_OTHERS.format(name="Syndicalism") in result.warnings
    assert result.statements[0].in_own_words is False
    assert syndicalism.readings == ()
    assert "## Syndicalism\n\n### Described by others" in llm.prompts[1].user


def test_marxism_is_added_when_the_model_leaves_it_out(database):
    llm = ScriptedLLM(
        "perspective: Anarchism | Peter Kropotkin | abolished government | Rejects the state.",
        COMPARISON,
    )
    result = make_service(database, llm).compare_traditions("executive committee")

    assert [p.name for p in result.perspectives] == ["Marxism", "Anarchism"]


def test_unsupported_lines_are_dropped_and_a_missing_disagreement_is_reported(database):
    reply = COMPARISON.replace("[1, 2]", "[2, 3]").replace("[1]", "[9]", 1)
    result = make_service(database, ScriptedLLM(TRADITIONS, reply)).compare_traditions("the state")

    assert result.disagreements == ()
    assert NO_DISAGREEMENT in result.warnings
    assert any("2 lines of the comparison did not cite" in w for w in result.warnings)
    assert result.statements_of("Marxism", StatementKind.POSITION) == []


def test_an_unreadable_comparison_still_offers_passages_and_readings(database):
    llm = ScriptedLLM(TRADITIONS, "Marxists and anarchists disagree about the state.")
    result = make_service(database, llm).compare_traditions("the state")

    assert result.status is TraditionsStatus.NOT_COMPARED
    assert COMPARISON_UNREADABLE in result.warnings
    assert len(result.sources) == 3
    assert [r.title for r in result.perspectives[1].readings] == ["The Conquest of Bread"]


def test_a_failed_comparison_call_still_offers_the_passages(database):
    llm = ScriptedLLM(TRADITIONS, LLMError("timeout"))
    result = make_service(database, llm).compare_traditions("the state")

    assert result.status is TraditionsStatus.NOT_COMPARED
    assert "The comparison could not be generated: timeout" in result.warnings


def test_the_reader_profile_shapes_the_comparison_prompt(database):
    profile = ReaderProfileService(SQLReaderProfileRepository(database))
    profile.correct_knowledge_assessment("anarchism", KnowledgeLevel.ADVANCED)
    llm = ScriptedLLM(TRADITIONS, COMPARISON)
    result = make_service(database, llm).compare_traditions("the state", profile.get_profile())

    assert result.personalized
    assert "Says they are at advanced level in anarchism" in llm.prompts[1].system


def test_without_a_model_or_a_topic_nothing_is_compared(database):
    with pytest.raises(TraditionsError, match="needs a language model"):
        make_service(database, None).compare_traditions("the state")
    assert NO_LLM_ERROR.startswith("Comparing traditions")
    with pytest.raises(TraditionsError, match="Name a topic"):
        make_service(database, ScriptedLLM()).compare_traditions("  ")
    with pytest.raises(TraditionsError, match="could not be read"):
        make_service(database, ScriptedLLM("Anarchism, mostly.")).compare_traditions("the state")
