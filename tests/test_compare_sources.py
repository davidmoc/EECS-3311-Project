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
    llm = ScriptedLLM(REPLY)
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
    prompt = llm.prompts[0]
    assert "### Source A: Marx, “Manifesto” (book)" in prompt.user
    assert "### Source B: Lenin, “State and Revolution” (book)" in prompt.user


def test_low_comparability_is_a_warning_first(database, books):
    manifesto, lenin, _ = books
    llm = ScriptedLLM("comparability: not comparable | one is about the state, one about revolution.")
    comparison = agent_for(database, llm).compare_sources(selections(manifesto, lenin), "the state")

    assert not comparison.is_comparable
    assert comparison.points == ()
    assert comparison.warnings[0] == (
        "These sources are not sufficiently comparable: one is about the state, "
        "one about revolution. A direct comparison could mislead."
    )


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
    llm = ScriptedLLM()
    comparison = agent_for(database, llm).compare_sources(selections(manifesto, cookbook), "the state")
    assert llm.prompts == []
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
    llm = ScriptedLLM(LLMError("timeout"))
    comparison = agent_for(database, llm).compare_sources(selections(manifesto, lenin), "the state")
    assert comparison.passages
    assert any("could not be generated: timeout" in w for w in comparison.warnings)


def test_unreadable_reply_keeps_the_passages(database, books):
    manifesto, lenin, _ = books
    llm = ScriptedLLM("Both texts discuss the state at length.")
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
    llm = ScriptedLLM("comparability: partly comparable | different scale")
    agent_for(database, llm).compare_sources(selections(manifesto, article), "the state")
    assert "Staff, “State budget passes” (news, published by Example Wire)" in llm.prompts[0].user
