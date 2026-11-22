import pytest

from praxis.agent import PromptBuilder, ResearchCorpus, reader_context
from praxis.agent.prompts import CITATION_NUMBER_RULE
from praxis.documents import Book
from praxis.reader_model import (
    AssessmentSource,
    ExplanationDepth,
    KnowledgeLevel,
    ReaderProfile,
)


def corpus_with(*texts):
    document = Book(
        title="The Communist Manifesto",
        author="Karl Marx and Friedrich Engels",
        text="\n\n".join(texts),
        license="Public Domain",
    )
    corpus = ResearchCorpus()
    for passage in document.passages():
        corpus.add_passage(document, passage)
    return corpus


def informed_profile():
    profile = ReaderProfile(background="Second-year history student")
    profile.knowledge.update_level("surplus value", KnowledgeLevel.ADVANCED, AssessmentSource.USER_STATED)
    profile.knowledge.update_level("imperialism", KnowledgeLevel.INTRODUCTORY)
    profile.interests.add("labour history")
    return profile


def test_question_prompt_numbers_and_cites_each_passage():
    corpus = corpus_with("Wages fall.", "The state is a committee.")

    prompt = PromptBuilder().build_question_prompt("Why do wages fall?", corpus)

    assert "Question: Why do wages fall?" in prompt.user
    assert "[1] Karl Marx and Friedrich Engels, “The Communist Manifesto”, ¶1\nWages fall." in prompt.user
    assert "[2] Karl Marx and Friedrich Engels, “The Communist Manifesto”, ¶2" in prompt.user
    assert "cite them inline" in prompt.system
    assert "About the reader" not in prompt.system


def test_question_prompt_needs_sources():
    with pytest.raises(ValueError):
        PromptBuilder().build_question_prompt("q", ResearchCorpus())


@pytest.mark.parametrize(
    "depth, phrase",
    [(ExplanationDepth.BRIEF, "two or three sentences"),
     (ExplanationDepth.DETAILED, "detailed explanation")],
)
def test_explanation_depth_follows_the_profile(depth, phrase):
    profile = ReaderProfile(explanation_depth=depth)

    prompt = PromptBuilder().build_question_prompt("q", corpus_with("x"), profile)

    assert phrase in prompt.system


def test_reader_context_describes_stated_and_inferred_knowledge_differently():
    context = reader_context(informed_profile())

    assert "In their own words: Second-year history student" in context
    assert "Says they are at advanced level in surplus value" in context
    assert "Probably at introductory level in imperialism (inferred from reading)" in context
    assert "Interested in: labour history" in context


def test_reader_context_is_included_in_the_question_prompt():
    prompt = PromptBuilder().build_question_prompt("q", corpus_with("x"), informed_profile())

    assert "About the reader:" in prompt.system
    assert "surplus value" in prompt.system


def test_no_reader_context_when_personalization_is_off():
    profile = informed_profile()
    profile.personalization_enabled = False

    assert reader_context(profile) is None


def test_no_reader_context_when_little_is_known():
    assert reader_context(ReaderProfile()) is None
    assert reader_context(None) is None


def test_search_terms_prompt_and_parsing():
    builder = PromptBuilder()

    prompt = builder.build_search_terms_prompt("What did Marx say about the state?")

    assert prompt.user == "What did Marx say about the state?"
    assert builder.parse_search_terms(
        'state, "ruling class", bourgeoisie\nstate; executive committee.'
    ) == ["state", "ruling class", "bourgeoisie", "executive committee"]
    assert builder.parse_search_terms(",".join(f"t{i}" for i in range(20))) == [
        f"t{i}" for i in range(8)
    ]
    assert builder.parse_search_terms(" , ") == []


def test_every_prompt_showing_passages_says_paragraph_numbers_are_not_citations():
    """A live run cited a passage's ¶310 as "[310]"."""
    book = Book(title="Revolution", author="Engels", text="The bourgeoisie made peace with the monarchy in 1848.", license="Public Domain")
    corpus = ResearchCorpus()
    corpus.add_passage(book, book.passages()[0])
    builder = PromptBuilder()

    prompts = [
        builder.build_question_prompt("Why?", corpus),
        builder.build_research_prompt("Why?", corpus, {}),
        builder.build_assessment_prompt("Why?", corpus, {}, established=[], searches_done=[]),
    ]

    assert all(CITATION_NUMBER_RULE in prompt.system for prompt in prompts)
