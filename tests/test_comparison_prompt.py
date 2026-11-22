"""PromptBuilder.build_comparison_prompt (F10)."""

import pytest

from praxis.agent.corpus import ResearchCorpus
from praxis.agent.prompts import CITATION_NUMBER_RULE, PromptBuilder
from praxis.comparison import SourceProfile
from praxis.documents import Book
from praxis.reader_model import KnowledgeLevel, ReaderProfile


@pytest.fixture
def sources():
    manifesto = Book(
        title="Manifesto", author="Marx",
        text="The state is a committee of the bourgeoisie.\n\nWages fall.",
        license="Public Domain",
    )
    lenin = Book(title="State and Revolution", author="Lenin", text="The state is an organ of class rule.")
    corpus = ResearchCorpus()
    first = [corpus.add_passage(manifesto, p) for p in manifesto.passages()]
    second = [corpus.add_passage(lenin, p) for p in lenin.passages()]
    return [
        (SourceProfile.of(manifesto).describe(), first),
        (SourceProfile.of(lenin).describe(), second),
    ]


def test_sources_are_lettered_and_passages_numbered_across_them(sources):
    prompt = PromptBuilder().build_comparison_prompt("the state", sources)

    assert prompt.user.startswith("Compare the sources on: the state")
    assert "### Source A: Marx, “Manifesto” (book)" in prompt.user
    assert "### Source B: Lenin, “State and Revolution” (book)" in prompt.user
    assert "[1] ¶1\nThe state is a committee" in prompt.user
    assert "[2] ¶2\nWages fall." in prompt.user
    assert "[3] ¶1\nThe state is an organ" in prompt.user


def test_rules_separate_facts_framing_and_interpretation(sources):
    system = PromptBuilder().build_comparison_prompt("the state", sources).system
    assert "comparability: <comparable|partly comparable|not comparable>" in system
    assert "A disagreement is about facts" in system
    # Live run: France and Austria were reported as a factual disagreement.
    assert "Claims about different countries, periods or groups do not" in system
    assert "interpretation, never stated as fact" in system
    assert "Do not state or guess who owns, funds" in system
    assert CITATION_NUMBER_RULE in system


def test_one_source_is_not_enough(sources):
    with pytest.raises(ValueError):
        PromptBuilder().build_comparison_prompt("the state", sources[:1])


def test_a_source_without_passages_is_refused(sources):
    with pytest.raises(ValueError):
        PromptBuilder().build_comparison_prompt("the state", [sources[0], ("Empty", [])])


def test_reader_context_is_added_when_known(sources):
    profile = ReaderProfile()
    profile.knowledge.update_level("the state", KnowledgeLevel.ADVANCED)
    prompt = PromptBuilder().build_comparison_prompt("the state", sources, profile)
    assert "About the reader:" in prompt.system
