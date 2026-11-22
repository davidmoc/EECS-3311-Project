"""AnnotationService.generate_annotation (F06, SD04)."""

import pytest
from conftest import ScriptedLLM

from praxis.documents import AnnotationType, Book
from praxis.llm import LLMError
from praxis.persistence import PassageMatch, SQLDocumentRepository
from praxis.reader_model import KnowledgeLevel, ReaderProfile
from praxis.reading import AnnotationError, AnnotationService, surrounding_passages
from praxis.reading.annotations import (
    NO_CONTEXT_WARNING,
    SHORT_PASSAGE_WORDS,
    UNSEEN_PARAGRAPH_WARNING,
)
from praxis.tools import PassageSearchTool, Tool, ToolManager, ToolResult

LONG = " ".join(["word"] * SHORT_PASSAGE_WORDS)


def tools_for(database):
    tools = ToolManager()
    tools.register_tool(PassageSearchTool(SQLDocumentRepository(database)))
    return tools


def manifesto(database):
    return next(
        d for d in SQLDocumentRepository(database).list_all() if "Manifesto" in d.title
    )


class BrokenSearch(Tool):
    name = "passage_search"
    description = "always fails"

    def validate(self, tool_input):
        return True

    def execute(self, tool_input):
        return ToolResult.failure(self.name, "index unavailable")


# --- surrounding text ----------------------------------------------------------


def test_long_passage_gets_one_paragraph_either_side():
    book = Book(title="T", author="A", text="\n\n".join(f"{LONG} {n}" for n in range(1, 8)))
    window = surrounding_passages(book, book.paragraph(4))
    assert [p.locator for p in window] == ["¶3", "¶4", "¶5"]


def test_short_passage_gets_a_wider_window():
    """UC06: an ambiguous passage is given more surrounding text."""
    paragraphs = [f"{LONG} {n}" for n in range(1, 8)]
    paragraphs[3] = "Short heading."
    book = Book(title="T", author="A", text="\n\n".join(paragraphs))
    window = surrounding_passages(book, book.paragraph(4))
    assert [p.locator for p in window] == ["¶2", "¶3", "¶4", "¶5", "¶6"]


def test_window_stops_at_the_start_and_end_of_the_text():
    book = Book(title="T", author="A", text=f"{LONG} a\n\n{LONG} b")
    assert [p.locator for p in surrounding_passages(book, book.paragraph(1))] == ["¶1", "¶2"]
    assert [p.locator for p in surrounding_passages(book, book.paragraph(2))] == ["¶1", "¶2"]


# --- generating ----------------------------------------------------------------


def test_terminology_annotation_does_not_search_the_library(library_database):
    tools = tools_for(library_database)
    llm = ScriptedLLM("The passage states that a patrician was a Roman noble.")
    book = manifesto(library_database)
    passage = book.paragraph(1)

    result = AnnotationService(tools, llm).generate_annotation(
        book, passage, AnnotationType.TERMINOLOGY
    )

    assert tools.call_count == 0
    assert not result.searched_library
    annotation = result.annotation
    assert annotation.content == "The passage states that a patrician was a Roman noble."
    assert annotation.passage_id == passage.id
    assert annotation.document_id == book.id
    assert annotation.locator == "¶1"
    assert annotation.type is AnnotationType.TERMINOLOGY
    assert annotation.sources == ()
    assert result.tokens_used == 15
    assert "Passage to annotate (¶1)" in llm.prompts[0].user


def test_historical_annotation_draws_on_other_texts(library_database):
    tools = tools_for(library_database)
    book = manifesto(library_database)
    passage = book.paragraph(3)  # the state as a committee of the bourgeoisie
    llm = ScriptedLLM("Engels describes the bourgeoisie making peace with the monarchy [1].")

    result = AnnotationService(tools, llm).generate_annotation(
        book, passage, AnnotationType.HISTORICAL_CONTEXT
    )

    assert result.searched_library
    titles = {c.document_title for c in result.annotation.sources}
    assert "Revolution and Counter-Revolution in Germany" in titles
    # The passage and the paragraphs around it are not repeated as sources.
    surrounding = {p.locator for p in surrounding_passages(book, passage)}
    assert not any(
        c.document_id == book.id and c.locator in surrounding
        for c in result.annotation.sources
    )
    assert "Other library passages:" in llm.prompts[0].user
    assert result.warnings == ()


def test_unknown_citation_is_warned_about(library_database):
    book = manifesto(library_database)
    llm = ScriptedLLM("See [1] and [7].")
    result = AnnotationService(tools_for(library_database), llm).generate_annotation(
        book, book.paragraph(3), AnnotationType.CONNECTION
    )
    assert any("[7]" in w and "not among its sources" in w for w in result.warnings)
    assert not any("[1]," in w for w in result.warnings)


def test_uncertainty_is_kept_on_the_annotation(library_database):
    book = manifesto(library_database)
    llm = ScriptedLLM(
        "The passage states a general law of history.\n"
        "uncertain: whether the authors meant societies before written history"
    )
    result = AnnotationService(tools_for(library_database), llm).generate_annotation(
        book, book.paragraph(1), AnnotationType.FACT_CHECK
    )
    assert result.annotation.is_uncertain
    assert result.annotation.uncertainties == (
        "whether the authors meant societies before written history",
    )
    assert "uncertain:" not in result.annotation.content


def test_reply_of_only_uncertainty_is_a_limitation_not_an_annotation(library_database):
    """SD04's "insufficient evidence" branch: show the limitation."""
    book = manifesto(library_database)
    llm = ScriptedLLM("uncertain: the passage gives no date or place to check")
    result = AnnotationService(tools_for(library_database), llm).generate_annotation(
        book, book.paragraph(2), AnnotationType.FACT_CHECK
    )
    assert result.annotation is None
    assert result.limitations == ("the passage gives no date or place to check",)


def test_failed_search_still_annotates_with_a_warning(library_database):
    tools = ToolManager()
    tools.register_tool(BrokenSearch())
    book = manifesto(library_database)
    result = AnnotationService(tools, ScriptedLLM("Background.")).generate_annotation(
        book, book.paragraph(1), AnnotationType.HISTORICAL_CONTEXT
    )
    assert result.annotation.content == "Background."
    assert any("index unavailable" in w for w in result.warnings)


def test_no_matching_passages_is_said(library_database):
    book = Book(title="Lone", author="A", text="Zyxwv qwerty uiopas.")
    llm = ScriptedLLM("Note.")
    result = AnnotationService(tools_for(library_database), llm).generate_annotation(
        book, book.paragraph(1), AnnotationType.CONNECTION
    )
    assert result.warnings == (NO_CONTEXT_WARNING,)
    assert "No other library passages were found" in llm.prompts[0].user


def test_reader_profile_personalizes_the_annotation(library_database):
    profile = ReaderProfile()
    profile.knowledge.update_level("class struggle", KnowledgeLevel.ADVANCED)
    book = manifesto(library_database)
    llm = ScriptedLLM("Note.")
    result = AnnotationService(tools_for(library_database), llm).generate_annotation(
        book, book.paragraph(1), AnnotationType.ARGUMENT, profile
    )
    assert result.annotation.personalized
    assert "About the reader:" in llm.prompts[0].system


def test_without_a_model_annotation_is_refused(library_database):
    book = manifesto(library_database)
    with pytest.raises(AnnotationError, match="No language model"):
        AnnotationService(tools_for(library_database)).generate_annotation(
            book, book.paragraph(1), AnnotationType.ARGUMENT
        )


def test_model_failure_is_reported(library_database):
    book = manifesto(library_database)
    llm = ScriptedLLM(LLMError("timeout"))
    with pytest.raises(AnnotationError, match="timeout"):
        AnnotationService(tools_for(library_database), llm).generate_annotation(
            book, book.paragraph(1), AnnotationType.ARGUMENT
        )


def test_passage_from_another_document_is_rejected(library_database):
    book = manifesto(library_database)
    other = Book(title="Other", author="B", text="Some text here.")
    with pytest.raises(ValueError):
        AnnotationService(tools_for(library_database), ScriptedLLM("x")).generate_annotation(
            book, other.paragraph(1), AnnotationType.ARGUMENT
        )


# --- paragraph references (found in a live run: "(see ¶3)" for an unseen ¶) -------


def test_paragraph_references_are_read_once_in_order():
    from praxis.reading.annotations import paragraph_references

    assert paragraph_references("See ¶12, then ¶ 3 and ¶12 again; [4] is not one.") == [12, 3]


def test_reference_to_an_unseen_paragraph_is_warned_about():
    paragraphs = [f"{LONG} {n}" for n in range(1, 10)]
    book = Book(title="T", author="A", text="\n\n".join(paragraphs))
    tools = ToolManager()
    llm = ScriptedLLM("As ¶4 and ¶6 show, and as ¶1 and ¶9 argue, this matters.")
    result = AnnotationService(tools, llm).generate_annotation(
        book, book.paragraph(5), AnnotationType.ARGUMENT
    )
    # ¶4-¶6 were shown as surrounding text; ¶1 and ¶9 were not.
    assert any(
        w.startswith("The annotation refers to ¶1, ¶9, which the model was not shown")
        for w in result.warnings
    )


class FixedSearch(Tool):
    """Returns one match: ¶40 of another text."""

    name = "passage_search"
    description = "fixed"

    def __init__(self, document):
        self.document = document

    def validate(self, tool_input):
        return True

    def execute(self, tool_input):
        return ToolResult.ok(self.name, [PassageMatch(self.document.paragraph(40), self.document, 1.0)])


def test_reference_to_a_source_paragraph_is_not_warned_about():
    book = Book(title="T", author="A", text="\n\n".join(f"{LONG} {n}" for n in range(1, 10)))
    other = Book(title="O", author="B", text="\n\n".join(f"{LONG} {n}" for n in range(1, 41)))
    tools = ToolManager()
    tools.register_tool(FixedSearch(other))
    llm = ScriptedLLM("Compare ¶40 of the other text [1], and ¶2.")
    result = AnnotationService(tools, llm).generate_annotation(
        book, book.paragraph(5), AnnotationType.CONNECTION
    )
    assert result.annotation.sources[0].locator == "¶40"
    assert result.warnings == (
        UNSEEN_PARAGRAPH_WARNING.format(labels="¶2", pronoun="it"),
    )


def test_prompt_forbids_references_to_unseen_paragraphs(library_database):
    book = manifesto(library_database)
    llm = ScriptedLLM("Note.")
    AnnotationService(tools_for(library_database), llm).generate_annotation(
        book, book.paragraph(1), AnnotationType.ARGUMENT
    )
    assert "Never refer to any other paragraph of the text" in llm.prompts[0].system
