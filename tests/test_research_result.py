"""The research synthesis prompt and ResearchResult (F03)."""

import pytest
from conftest import MANIFESTO_PASSAGES, REVOLUTION_PASSAGES

from praxis.agent import PromptBuilder, ResearchCorpus, ResponseStatus
from praxis.documents import Book
from praxis.research import ResearchSession
from praxis.research.result import Reading, ResearchResult

MANIFESTO = Book(
    title="The Communist Manifesto",
    author="Karl Marx and Friedrich Engels",
    text="\n\n".join(MANIFESTO_PASSAGES),
    license="Public Domain",
)
GERMANY = Book(
    title="Revolution and Counter-Revolution in Germany",
    author="Friedrich Engels",
    text="\n\n".join(REVOLUTION_PASSAGES),
    license="Public Domain",
)


@pytest.fixture
def corpus():
    corpus = ResearchCorpus()
    corpus.add_passage(GERMANY, GERMANY.passages()[0])      # [1]
    corpus.add_passage(MANIFESTO, MANIFESTO.passages()[0])  # [2]
    corpus.add_passage(GERMANY, GERMANY.passages()[1])      # [3]
    return corpus


def test_research_prompt_groups_sources_by_purpose(corpus):
    prompt = PromptBuilder().build_research_prompt(
        "Why did 1848 fail?", corpus, {1: "history", 2: "theory", 3: "history"}
    )

    history = prompt.user.index("### Retrieved for historical development")
    theory = prompt.user.index("### Retrieved for theoretical background")
    assert history < prompt.user.index("[1] Friedrich Engels") < prompt.user.index("[3] ") < theory
    assert prompt.user.index("[2] Karl Marx") > theory
    assert prompt.user.startswith("Research question: Why did 1848 fail?")
    assert "## Open questions" in prompt.system
    assert "stopped before" not in prompt.user


def test_research_prompt_says_when_research_was_cut_short(corpus):
    prompt = PromptBuilder().build_research_prompt(
        "Why did 1848 fail?", corpus, {}, unfinished="the time limit was reached"
    )

    assert "Research stopped before every planned step ran: the time limit was reached" in prompt.user
    assert "### Retrieved as evidence on the question" in prompt.user  # unknown purpose


def test_research_prompt_needs_sources():
    with pytest.raises(ValueError):
        PromptBuilder().build_research_prompt("anything", ResearchCorpus(), {})


def test_open_questions_are_split_from_the_synthesis():
    text = (
        "## Findings\nThe bourgeoisie made peace with the monarchy [1].\n\n"
        "## Open questions\n- Why did the peasantry stay passive?\n"
        "* What role did Prussia play?\n\nSome trailing remark.\n"
    )

    body, questions = PromptBuilder.split_open_questions(text)

    assert body == "## Findings\nThe bourgeoisie made peace with the monarchy [1]."
    assert questions == ["Why did the peasantry stay passive?", "What role did Prussia play?"]


def test_sections_after_open_questions_stay_in_the_body():
    body, questions = PromptBuilder.split_open_questions(
        "## Findings\nA [1].\n## Open questions\n- Q1?\n## Theoretical connections\nB [2]."
    )

    assert questions == ["Q1?"]
    assert body.endswith("## Theoretical connections\nB [2].")


def test_synthesis_without_the_heading_is_left_whole():
    assert PromptBuilder.split_open_questions(" Just prose [1]. ") == ("Just prose [1].", [])


def test_recommended_readings_follow_the_cited_texts_once_each(corpus):
    sources = tuple(corpus.sources)
    result = ResearchResult(
        ResearchSession("1848"), ResponseStatus.ANSWERED, None,
        sources=sources, cited=(sources[2], sources[0], sources[1]),
    )

    assert result.is_grounded
    assert [r.title for r in result.get_recommended_readings()] == [
        "Revolution and Counter-Revolution in Germany",
        "The Communist Manifesto",
    ]
    assert [c.locator for c in result.get_citations()] == ["¶2", "¶1", "¶1"]


def test_without_citations_every_source_text_is_suggested(corpus):
    session = ResearchSession("1848")
    session.add_warning("no model")
    result = ResearchResult(
        session, ResponseStatus.EXPLANATION_FAILED, None, sources=tuple(corpus.sources)
    )

    assert not result.is_grounded
    assert result.objective == "1848"
    assert result.warnings == ("no model",)
    assert result.get_recommended_readings()[0] == Reading(
        GERMANY.id, GERMANY.title, GERMANY.author
    )
