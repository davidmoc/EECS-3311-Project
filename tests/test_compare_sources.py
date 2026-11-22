"""CompareSourcesCommand and PoliticalResearchAgent.compare_sources (F10, SD06)."""

import pytest
from conftest import ScriptedLLM

from praxis.agent import AgentError, PoliticalResearchAgent
from praxis.agent.agent import COMPARISON_UNREADABLE, NO_LLM_WARNING, TOO_FEW_TO_COMPARE
from praxis.comparison import Comparability, PointKind, SourceSelection
from praxis.comparison.command import CompareSourcesCommand
from praxis.documents import Book, NewsArticle
from praxis.llm import LLMError
from praxis.persistence import Database, SQLDocumentRepository, SQLReaderProfileRepository
from praxis.persistence.comparisons import SQLComparisonRepository
from praxis.persistence.research import SQLResearchRepository
from praxis.reader_model.service import ReaderProfileService
from praxis.research.commands import ResearchContext
from praxis.research.session import ResearchSession
from praxis.tools import ToolFactory, ToolManager

MARX = (
    "The executive of the modern state is but a committee for managing the common affairs of the whole bourgeoisie.",
    "The proletariat will use its political supremacy to wrest all capital from the bourgeoisie.",
)
LENIN = (
    "The state is a product and a manifestation of the irreconcilability of class antagonisms.",
    "The state is an organ of class rule, an organ for the oppression of one class by another.",
)
COOKING = ("Boil the potatoes until soft, then mash them with butter.",)


@pytest.fixture
def database():
    database = Database()
    yield database
    database.close()


@pytest.fixture
def books(database):
    documents = SQLDocumentRepository(database)
    made = []
    for title, author, paragraphs in (
        ("Manifesto", "Marx", MARX),
        ("State and Revolution", "Lenin", LENIN),
        ("Cookbook", "Anon", COOKING),
    ):
        book = Book(title=title, author=author, text="\n\n".join(paragraphs), license="Public Domain")
        documents.save(book)
        made.append(book)
    return made


def agent_for(database, llm=None):
    tools = ToolManager()
    for tool in ToolFactory(SQLDocumentRepository(database)).create_all():
        tools.register_tool(tool)
    profiles = ReaderProfileService(SQLReaderProfileRepository(database))
    return PoliticalResearchAgent(tools, profiles, llm)


def selections(*documents):
    return [SourceSelection.of(document) for document in documents]


# --- the command -----------------------------------------------------------------


def test_command_retrieves_each_source_through_the_tool(database, books):
    manifesto, lenin, _ = books
    tools = agent_for(database)._tools
    context = ResearchContext(ResearchSession("the state"), tools)
    command = CompareSourcesCommand("the state", tuple(selections(manifesto, lenin)))

    outcome = command.execute(context)

    assert outcome.succeeded
    assert context.session.tool_call_count == 2  # one retrieval per source
    titles = [s.citation.document_title for s in context.corpus.sources]
    assert titles[0] == "Manifesto" and set(titles[1:]) == {"State and Revolution"}
    assert set(context.purposes.values()) == {"comparison"}


def test_command_reports_a_source_with_nothing_on_the_subject(database, books):
    manifesto, _, cookbook = books
    tools = agent_for(database)._tools
    context = ResearchContext(ResearchSession("the state"), tools)
    CompareSourcesCommand("the state", tuple(selections(manifesto, cookbook))).execute(context)
    assert any("“Cookbook”" in w and "left out" in w for w in context.session.warnings)


def test_command_equality_includes_the_sources(books):
    manifesto, lenin, cookbook = books
    a = CompareSourcesCommand("state", tuple(selections(manifesto, lenin)))
    assert a == CompareSourcesCommand("state", tuple(selections(manifesto, lenin)))
    assert a != CompareSourcesCommand("state", tuple(selections(manifesto, cookbook)))
    assert a.retry().attempt == 2 and a.retry().selections == a.selections


# --- the agent -------------------------------------------------------------------

KEYWORDS = "state, class rule"

REPLY = """\
comparability: comparable | both define the state by class rule
similarity: both tie the state to class rule [1, 3]
difference: terminology | Marx says "committee", Lenin says "organ of oppression" [1, 4]
difference: emphasis | only the Manifesto is cited here [1, 2]
observation: Lenin writes as a polemicist against reformists [3]
uncertain: whether Lenin had the Manifesto passage in mind
"""


def test_comparison_cites_passages_of_both_sources(database, books):
    manifesto, lenin, _ = books
    llm = ScriptedLLM(REPLY)  # every paragraph is named, so no keyword call
    # Named paragraphs fix the numbering: [1], [2] are Marx's, [3], [4] Lenin's.
    comparison = agent_for(database, llm).compare_sources(
        [SourceSelection.of(manifesto, (1, 2)), SourceSelection.of(lenin, (1, 2))], "the state"
    )

    assert [p.number for p in comparison.passages] == [1, 2, 3, 4]
    assert [p.title for p in comparison.profiles] == ["Manifesto", "State and Revolution"]
    assert comparison.comparability is Comparability.COMPARABLE
    assert [p.kind for p in comparison.points] == [
        PointKind.SIMILARITY, PointKind.DIFFERENCE, PointKind.OBSERVATION,
    ]
    assert comparison.differences[0].aspect == "terminology"
    assert comparison.uncertainties == ("whether Lenin had the Manifesto passage in mind",)
    # The difference citing only the Manifesto is dropped, and the reader told.
    assert any("1 point of the comparison" in w for w in comparison.warnings)
    assert comparison.tokens_used == 15
    assert len(llm.prompts) == 1
    prompt = llm.prompts[0]
    assert "### Source A: Marx, “Manifesto” (book)" in prompt.user
    assert "### Source B: Lenin, “State and Revolution” (book)" in prompt.user


def test_low_comparability_is_a_warning_first(database, books):
    manifesto, lenin, _ = books
    llm = ScriptedLLM(KEYWORDS, "comparability: not comparable | one is about the state, one about revolution.")
    comparison = agent_for(database, llm).compare_sources(selections(manifesto, lenin), "the state")

    assert not comparison.is_comparable
    assert comparison.points == ()
    assert comparison.warnings[0] == (
        "These sources are not sufficiently comparable: one is about the state, "
        "one about revolution. A direct comparison could mislead."
    )


def test_the_models_keywords_find_a_source_that_names_the_subject_differently(database, books):
    """Live run: De Leon's Brumaire says "allotment farmers", not "peasantry"."""
    manifesto, _, _ = books
    brumaire = Book(
        title="Brumaire", author="Marx", license="Public Domain",
        text="The allotment farmers were ruined by the mortgage and the tax collector.",
    )
    SQLDocumentRepository(database).save(brumaire)
    manifesto_on_peasants = Book(
        title="Programme", author="Engels", license="Public Domain",
        text="The peasantry is a class doomed by large-scale production.",
    )
    SQLDocumentRepository(database).save(manifesto_on_peasants)
    llm = ScriptedLLM("peasants, allotment, small farmers", "comparability: comparable | both")

    comparison = agent_for(database, llm).compare_sources(
        selections(manifesto_on_peasants, brumaire), "the peasantry"
    )

    assert [p.title for p in comparison.profiles] == ["Programme", "Brumaire"]
    assert "the peasantry" in llm.prompts[0].user  # the keywords prompt


def test_named_paragraphs_need_no_subject(database, books):
    manifesto, lenin, _ = books
    llm = ScriptedLLM(REPLY)
    comparison = agent_for(database, llm).compare_sources(
        [SourceSelection.of(manifesto, (2,)), SourceSelection.of(lenin, (1,))]
    )
    assert comparison.subject == "the selected passages"
    assert [p.citation.locator for p in comparison.passages] == ["¶2", "¶1"]


def test_a_whole_source_needs_a_subject(database, books):
    manifesto, lenin, _ = books
    with pytest.raises(AgentError, match="what to compare"):
        agent_for(database).compare_sources(
            [SourceSelection.of(manifesto, (1,)), SourceSelection.of(lenin)]
        )


def test_one_source_is_refused(database, books):
    manifesto, _, _ = books
    with pytest.raises(AgentError, match="two different sources"):
        agent_for(database).compare_sources(
            [SourceSelection.of(manifesto, (1,)), SourceSelection.of(manifesto, (2,))]
        )


def test_too_many_sources_are_refused(database, books):
    documents = SQLDocumentRepository(database)
    extra = []
    for n in range(3):
        book = Book(title=f"Extra {n}", author="A", text="The state again.", license="Public Domain")
        documents.save(book)
        extra.append(book)
    with pytest.raises(AgentError, match="at most 4"):
        agent_for(database).compare_sources(selections(*books[:2], *extra), "state")


def test_without_two_sources_with_passages_the_model_is_not_asked(database, books):
    manifesto, _, cookbook = books
    llm = ScriptedLLM(KEYWORDS)
    comparison = agent_for(database, llm).compare_sources(selections(manifesto, cookbook), "the state")
    assert len(llm.prompts) == 1  # only the search keywords were asked for
    assert TOO_FEW_TO_COMPARE in comparison.warnings
    assert [p.title for p in comparison.profiles] == ["Manifesto"]


def test_without_a_model_the_passages_are_still_returned(database, books):
    manifesto, lenin, _ = books
    comparison = agent_for(database).compare_sources(selections(manifesto, lenin), "the state")
    assert len(comparison.passages) >= 2
    assert not comparison.has_analysis
    assert NO_LLM_WARNING in comparison.warnings


def test_model_failure_keeps_the_passages(database, books):
    manifesto, lenin, _ = books
    llm = ScriptedLLM(KEYWORDS, LLMError("timeout"))
    comparison = agent_for(database, llm).compare_sources(selections(manifesto, lenin), "the state")
    assert comparison.passages
    assert any("could not be generated: timeout" in w for w in comparison.warnings)


def test_unreadable_reply_keeps_the_passages(database, books):
    manifesto, lenin, _ = books
    llm = ScriptedLLM(KEYWORDS, "Both texts discuss the state at length.")
    comparison = agent_for(database, llm).compare_sources(selections(manifesto, lenin), "the state")
    assert comparison.points == ()
    assert COMPARISON_UNREADABLE in comparison.warnings


def test_news_outlet_reaches_the_prompt(database, books):
    manifesto, _, _ = books
    article = NewsArticle(
        title="State budget passes", author="Staff", outlet="Example Wire",
        text="The state budget passed after the ruling class parties agreed.", license="",
    )
    SQLDocumentRepository(database).save(article)
    llm = ScriptedLLM(KEYWORDS, "comparability: partly comparable | different scale")
    agent_for(database, llm).compare_sources(selections(manifesto, article), "the state")
    assert "Staff, “State budget passes” (news, published by Example Wire)" in llm.prompts[1].user


# --- storing, reopening, and comparing from research -------------------------------


def stored_agent(database, llm=None):
    tools = ToolManager()
    for tool in ToolFactory(SQLDocumentRepository(database)).create_all():
        tools.register_tool(tool)
    return PoliticalResearchAgent(
        tools,
        ReaderProfileService(SQLReaderProfileRepository(database)),
        llm,
        research_repository=SQLResearchRepository(database),
        comparison_repository=SQLComparisonRepository(database),
    )


def test_a_comparison_is_stored_and_can_be_reopened(database, books):
    manifesto, lenin, _ = books
    comparison = stored_agent(database, ScriptedLLM(KEYWORDS, REPLY)).compare_sources(
        selections(manifesto, lenin), "the state"
    )
    agent = stored_agent(database)
    found = agent.find_comparison(str(comparison.id)[:8])
    assert agent.get_comparison(found) == comparison
    assert [s.subject for s in agent.list_comparisons()] == ["the state"]


def test_a_comparison_of_fewer_than_two_sources_is_not_stored(database, books):
    manifesto, _, cookbook = books
    agent = stored_agent(database, ScriptedLLM(KEYWORDS))
    agent.compare_sources(selections(manifesto, cookbook), "the state")
    assert agent.list_comparisons() == []


def test_unknown_comparison_ids_are_reported(database, books):
    agent = stored_agent(database)
    with pytest.raises(AgentError, match="No comparison"):
        agent.find_comparison("abc")


def test_research_sources_are_compared_on_the_research_question(library_database):
    plan = "history: 1848 revolution Germany\ntheory: bourgeoisie state"
    synthesis = "## Findings\nThe bourgeoisie made peace with the monarchy [1]."
    research = stored_agent(library_database, ScriptedLLM(plan, "verdict: sufficient", synthesis)).research(
        "Why did the German revolution of 1848 fail?"
    )
    titles = {s.citation.document_title for s in research.sources}
    assert len(titles) == 2  # the research drew on both texts

    llm = ScriptedLLM("comparability: comparable | same events")
    comparison = stored_agent(library_database, llm).compare_research_sources(research.session.id)

    assert comparison.subject == research.objective
    assert {p.title for p in comparison.profiles} == titles
    # The research's own passages are compared, so no keyword search is made.
    assert len(llm.prompts) == 1
    assert {s.passage.id for s in comparison.passages} == {s.passage.id for s in research.sources}


def test_research_on_one_text_cannot_be_compared(library_database):
    plan = "evidence: wage labour subsistence"
    research = stored_agent(library_database, ScriptedLLM(plan, "verdict: sufficient", "## Findings\nWages [1].")).research(
        "What are wages?"
    )
    assert {s.citation.document_title for s in research.sources} == {"The Communist Manifesto"}
    with pytest.raises(AgentError, match="only one text"):
        stored_agent(library_database).compare_research_sources(research.session.id)


def test_paragraphs_beyond_the_limit_are_reported(database):
    """Live run: research with 16 passages from one book was cut to 6 silently."""
    documents = SQLDocumentRepository(database)
    long = Book(title="Long", author="A", license="Public Domain",
                text="\n\n".join(f"The state, part {n}." for n in range(1, 10)))
    short = Book(title="Short", author="B", license="Public Domain", text="The state.")
    documents.save(long)
    documents.save(short)

    comparison = agent_for(database).compare_sources(
        [SourceSelection.of(long, tuple(range(1, 10))), SourceSelection.of(short, (1,))]
    )

    assert len(comparison.passages_of(comparison.profiles[0])) == 6
    assert "9 paragraphs of “Long” were named; only the first 6 (¶1, ¶2, ¶3, ¶4, ¶5, ¶6) were compared." in comparison.warnings
