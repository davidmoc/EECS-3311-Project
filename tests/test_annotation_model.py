from uuid import uuid4

import pytest

from praxis.documents import Annotation, AnnotationType, Book


def make_book():
    return Book(
        title="Manifesto",
        author="Marx and Engels",
        text="First paragraph here.\n\nSecond paragraph here.\n\nThird one.",
        license="Public Domain",
    )


@pytest.mark.parametrize(
    "name",
    ["historical_context", "historical-context", "Historical Context", "  HISTORICAL-context "],
)
def test_parse_accepts_the_spellings_a_reader_would_type(name):
    assert AnnotationType.parse(name) is AnnotationType.HISTORICAL_CONTEXT


def test_parse_rejects_unknown_types_and_lists_the_choices():
    with pytest.raises(ValueError, match="fact-check"):
        AnnotationType.parse("summary")


def test_label_is_readable():
    assert AnnotationType.FACT_CHECK.label == "fact check"


def test_only_context_dependent_types_search_the_library():
    searching = {t for t in AnnotationType if t.searches_library}
    assert searching == {
        AnnotationType.HISTORICAL_CONTEXT,
        AnnotationType.FACT_CHECK,
        AnnotationType.CONNECTION,
    }


def test_annotation_without_content_is_rejected():
    with pytest.raises(ValueError):
        Annotation(passage_id=uuid4(), type=AnnotationType.ARGUMENT, content="  ")


def test_annotation_stores_tuples_and_reports_uncertainty():
    annotation = Annotation(
        passage_id=uuid4(),
        type=AnnotationType.FACT_CHECK,
        content="The date is given in the text.",
        uncertainties=["The casualty figure is not in any source."],
    )
    assert annotation.uncertainties == ("The casualty figure is not in any source.",)
    assert annotation.is_uncertain
    assert not Annotation(
        passage_id=uuid4(), type=AnnotationType.ARGUMENT, content="x"
    ).is_uncertain


def test_paragraph_returns_the_numbered_passage():
    book = make_book()
    assert book.paragraph(2).text == "Second paragraph here."
    assert book.paragraph(2).locator == "¶2"


@pytest.mark.parametrize("number", [0, 4])
def test_paragraph_out_of_range_names_the_paragraph_count(number):
    with pytest.raises(ValueError, match="has 3 paragraphs"):
        make_book().paragraph(number)
