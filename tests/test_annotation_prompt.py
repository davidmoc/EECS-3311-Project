from datetime import date

import pytest

from praxis.agent.corpus import ResearchCorpus
from praxis.agent.prompts import CITATION_NUMBER_RULE, PromptBuilder
from praxis.documents import AnnotationType, Book
from praxis.reader_model import ExplanationDepth, ReaderProfile

TEXT = (
    "The history of all hitherto existing society is the history of class struggles.\n\n"
    "Freeman and slave, patrician and plebeian, lord and serf, in a word, "
    "oppressor and oppressed.\n\n"
    "The modern bourgeois society has not done away with class antagonisms."
)


@pytest.fixture
def book():
    return Book(
        title="Manifesto of the Communist Party",
        author="Marx and Engels",
        text=TEXT,
        license="Public Domain",
        publication_date=date(1848, 2, 21),
    )


@pytest.fixture
def other():
    return Book(
        title="Revolution and Counter-Revolution",
        author="Engels",
        text="The patricians of Rome held the plebeians in debt bondage.",
        license="Public Domain",
    )


@pytest.mark.parametrize("annotation_type", list(AnnotationType))
def test_every_type_has_a_task(book, annotation_type):
    prompt = PromptBuilder().build_annotation_prompt(
        book, book.paragraph(2), book.passages(), annotation_type
    )
    assert "Task: " in prompt.system


def test_passage_is_marked_among_its_surroundings(book):
    passage = book.paragraph(2)
    prompt = PromptBuilder().build_annotation_prompt(
        book, passage, book.passages(), AnnotationType.TERMINOLOGY
    )
    assert "“Manifesto of the Communist Party” (1848), by Marx and Engels" in prompt.user
    assert f"Passage to annotate (¶2):\n<<<\n{passage.text}\n>>>" in prompt.user
    assert "(¶1) The history of all" in prompt.user
    assert "(¶3) The modern bourgeois" in prompt.user
    # Surroundings stay in reading order around the passage.
    assert prompt.user.index("(¶1)") < prompt.user.index("¶2") < prompt.user.index("(¶3)")


def test_passage_missing_from_surroundings_is_still_annotated(book):
    passage = book.paragraph(2)
    prompt = PromptBuilder().build_annotation_prompt(
        book, passage, [], AnnotationType.ARGUMENT
    )
    assert "Passage to annotate (¶2)" in prompt.user


def test_library_passages_are_numbered_for_citation(book, other):
    corpus = ResearchCorpus()
    corpus.add_passage(other, other.passages()[0])
    prompt = PromptBuilder().build_annotation_prompt(
        book, book.paragraph(2), book.passages(), AnnotationType.CONNECTION, corpus
    )
    assert "Other library passages:" in prompt.user
    assert "[1] Engels, “Revolution and Counter-Revolution”, ¶1" in prompt.user
    assert CITATION_NUMBER_RULE in prompt.system


def test_without_library_passages_the_model_is_told_so(book):
    prompt = PromptBuilder().build_annotation_prompt(
        book, book.paragraph(1), book.passages(), AnnotationType.HISTORICAL_CONTEXT,
        ResearchCorpus(),
    )
    assert "No other library passages were found" in prompt.user


def test_reader_depth_is_applied(book):
    profile = ReaderProfile(explanation_depth=ExplanationDepth.BRIEF)
    prompt = PromptBuilder().build_annotation_prompt(
        book, book.paragraph(1), book.passages(), AnnotationType.ARGUMENT, profile=profile
    )
    assert "two or three sentences" in prompt.system


def test_parse_annotation_splits_off_uncertainty_lines():
    content, uncertain = PromptBuilder.parse_annotation(
        "The passage states that history is class struggle.\n\n"
        "This suggests a general law.\n"
        "uncertain: whether Marx meant prehistory too\n"
        "- Uncertain: the date of the first draft\n"
        "uncertain: whether Marx meant prehistory too\n"
        "uncertain:   \n"
    )
    assert content == (
        "The passage states that history is class struggle.\n\nThis suggests a general law."
    )
    assert uncertain == ["whether Marx meant prehistory too", "the date of the first draft"]


def test_parse_annotation_without_uncertainty():
    assert PromptBuilder.parse_annotation("  Plain note.  ") == ("Plain note.", [])
