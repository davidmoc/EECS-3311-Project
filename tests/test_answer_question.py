"""PoliticalResearchAgent.answer_question (F04, SD02)."""

import pytest

from praxis.agent import (
    AgentError,
    PoliticalResearchAgent,
    ResearchCorpus,
    ResponseStatus,
    check_citations,
)
from praxis.documents import Book
from praxis.llm import LLMClient, LLMError, LLMResponse
from praxis.persistence import Database, SQLDocumentRepository, SQLReaderProfileRepository
from praxis.reader_model import KnowledgeLevel
from praxis.reader_model.service import ReaderProfileService
from praxis.tools import PassageSearchTool, Tool, ToolManager, ToolResult

WAGES = (
    "The average price of wage labour is the minimum wage, the quantum of "
    "the means of subsistence requisite to keep the labourer in existence."
)
STATE = (
    "The executive of the modern state is but a committee for managing the "
    "common affairs of the whole bourgeoisie."
)


class FakeLLM(LLMClient):
    """Replies in order; an LLMError in the list is raised instead."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(reply, "fake", prompt_tokens=10, completion_tokens=5)


class BrokenSearch(Tool):
    name = "passage_search"
    description = "always fails"

    def validate(self, tool_input):
        return True

    def execute(self, tool_input):
        return ToolResult.failure(self.name, "index unavailable")


@pytest.fixture
def database():
    database = Database()
    SQLDocumentRepository(database).save(
        Book(
            title="The Communist Manifesto",
            author="Karl Marx and Friedrich Engels",
            text=f"{WAGES}\n\n{STATE}",
            license="Public Domain",
        )
    )
    yield database
    database.close()


@pytest.fixture
def profiles(database):
    return ReaderProfileService(SQLReaderProfileRepository(database))


def make_agent(database, profiles, llm, tool=None):
    tools = ToolManager()
    tools.register_tool(tool or PassageSearchTool(SQLDocumentRepository(database)))
    return PoliticalResearchAgent(tools, profiles, llm)


def test_answer_cites_the_retrieved_passages(database, profiles):
    llm = FakeLLM("minimum wage, subsistence", "Wages tend to subsistence [1].")

    response = make_agent(database, profiles, llm).answer_question("Why are wages low?")

    assert response.status is ResponseStatus.ANSWERED
    assert response.is_grounded
    assert response.search_terms == ("minimum wage", "subsistence")
    assert response.sources[0].citation.quoted_text == WAGES
    assert [s.number for s in response.cited] == [1]
    assert response.explanation == "Wages tend to subsistence [1]."
    assert response.warnings == ()
    assert response.tokens_used == 30
    # the passage text reaches the model, numbered
    assert f"[1] Karl Marx and Friedrich Engels, “The Communist Manifesto”, ¶1\n{WAGES}" in llm.prompts[1].user


def test_no_sources_means_no_generated_answer(database, profiles):
    llm = FakeLLM("tariffs, trade")

    response = make_agent(database, profiles, llm).answer_question("What about tariffs?")

    assert response.status is ResponseStatus.NO_SOURCES
    assert response.explanation is None
    assert response.sources == ()
    assert "No passage in the library addresses this question" in response.warnings[-1]
    assert len(llm.prompts) == 1  # only the keyword step; nothing was explained


def test_llm_failure_still_returns_the_passages(database, profiles):
    llm = FakeLLM("wage", LLMError("rate limited"))

    response = make_agent(database, profiles, llm).answer_question("wages?")

    assert response.status is ResponseStatus.EXPLANATION_FAILED
    assert response.sources
    assert response.explanation is None
    assert "rate limited" in response.warnings[-1]


def test_keyword_failure_falls_back_to_the_question(database, profiles):
    llm = FakeLLM(LLMError("timeout"), "The state serves the bourgeoisie [1].")

    response = make_agent(database, profiles, llm).answer_question("What is the state?")

    assert response.status is ResponseStatus.ANSWERED
    assert response.search_terms == ()
    assert response.sources[0].citation.quoted_text == STATE


def test_without_an_llm_only_passages_are_returned(database, profiles):
    response = make_agent(database, profiles, None).answer_question("the state")

    assert response.status is ResponseStatus.EXPLANATION_FAILED
    assert response.sources[0].citation.quoted_text == STATE
    assert "OPENAI_API_KEY" in response.warnings[-1]


def test_citations_to_missing_sources_are_flagged(database, profiles):
    llm = FakeLLM("wage", "Wages fall [1], as Ricardo showed [7].")

    response = make_agent(database, profiles, llm).answer_question("wages?")

    assert [s.number for s in response.cited] == [1]
    assert "[7], which is not among the sources" in response.warnings[0]


def test_uncited_explanation_is_flagged(database, profiles):
    llm = FakeLLM("wage", "Wages fall because of competition.")

    response = make_agent(database, profiles, llm).answer_question("wages?")

    assert response.status is ResponseStatus.ANSWERED
    assert not response.is_grounded
    assert "does not cite any passage" in response.warnings[-1]


def test_failed_search_is_reported(database, profiles):
    llm = FakeLLM("wage")

    response = make_agent(database, profiles, llm, BrokenSearch()).answer_question("wages?")

    assert response.status is ResponseStatus.NO_SOURCES
    assert "Library search failed: index unavailable" in response.warnings[0]


def test_reader_profile_shapes_the_prompt(database, profiles):
    profiles.correct_knowledge_assessment("political economy", KnowledgeLevel.ADVANCED)
    llm = FakeLLM("wage", "Explained [1].")

    response = make_agent(database, profiles, llm).answer_question("wages?")

    assert response.personalized
    assert "advanced level in political economy" in llm.prompts[1].system


def test_sparse_profile_is_not_called_personalized(database, profiles):
    llm = FakeLLM("wage", "Explained [1].")

    response = make_agent(database, profiles, llm).answer_question("wages?")

    assert not response.personalized
    assert "About the reader" not in llm.prompts[1].system


def test_passages_are_not_repeated_across_queries(database, profiles):
    # keywords and the question both find the wages passage
    llm = FakeLLM("wage", "Explained [1].")

    response = make_agent(database, profiles, llm).answer_question("minimum wage")

    assert [s.citation.locator for s in response.sources] == ["¶1"]


def test_empty_question_is_rejected(database, profiles):
    with pytest.raises(AgentError):
        make_agent(database, profiles, FakeLLM()).answer_question("   ")


def test_check_citations_handles_grouped_and_repeated_marks():
    document = Book(title="T", author="A", text="a\n\nb\n\nc")
    corpus = ResearchCorpus()
    for passage in document.passages():
        corpus.add_passage(document, passage)

    cited, unknown = check_citations("x [3, 1] y [1] z [9] w [2024 is a year]", corpus)

    assert [s.number for s in cited] == [3, 1]
    assert unknown == [9]
