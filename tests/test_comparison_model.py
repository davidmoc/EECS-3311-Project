"""SourceProfile, SourceComparison and reading the model's comparison (F10)."""

from datetime import date

import pytest

from praxis.agent import ResearchCorpus
from praxis.comparison import (
    Comparability,
    ComparisonPoint,
    PointKind,
    SourceComparison,
    SourceProfile,
    SourceSelection,
    check_points,
    parse_comparison,
)
from praxis.documents import Book, NewsArticle


def test_profile_holds_only_the_documents_metadata():
    article = NewsArticle(
        title="Strike ends", author="Staff", outlet="Daily Wire Service",
        publication_date=date(2026, 11, 3), source_url="https://example.org/a",
    )
    profile = SourceProfile.of(article)
    assert profile.kind == "news"
    assert profile.outlet == "Daily Wire Service"
    assert profile.describe() == "Staff, “Strike ends” (news, published by Daily Wire Service, 2026)"


def test_profile_of_a_book_has_no_outlet():
    profile = SourceProfile.of(Book(title="State and Revolution", author="Lenin"))
    assert profile.describe() == "Lenin, “State and Revolution” (book)"


def test_selection_rejects_paragraph_zero():
    with pytest.raises(ValueError):
        SourceSelection(Book(title="T", author="A").id, (0,))


def comparison_of_two_books():
    a = Book(title="A", author="X", text="one\n\ntwo", license="Public Domain")
    b = Book(title="B", author="Y", text="three", license="Public Domain")
    corpus = ResearchCorpus()
    for document in (a, b):
        for passage in document.passages():
            corpus.add_passage(document, passage)
    return SourceComparison(
        "subject",
        (SourceProfile.of(a), SourceProfile.of(b)),
        tuple(corpus.sources),
        points=(
            ComparisonPoint(PointKind.SIMILARITY, "both", (1, 3)),
            ComparisonPoint(PointKind.OBSERVATION, "A frames it", (2,)),
        ),
        comparability=Comparability.COMPARABLE,
    )


def test_comparison_knows_which_source_each_passage_came_from():
    comparison = comparison_of_two_books()
    assert comparison.source_of(1).title == "A"
    assert comparison.source_of(3).title == "B"
    assert comparison.source_of(9) is None
    assert [p.number for p in comparison.passages_of(comparison.profiles[0])] == [1, 2]
    assert [p.description for p in comparison.similarities] == ["both"]
    assert [p.description for p in comparison.observations] == ["A frames it"]
    assert comparison.is_comparable


def test_comparability_words():
    assert Comparability.parse("Not comparable") is Comparability.LOW
    assert Comparability.parse("low") is Comparability.LOW
    assert Comparability.parse("partly comparable") is Comparability.PARTLY
    assert Comparability.parse("comparable") is Comparability.COMPARABLE
    assert Comparability.parse("maybe") is None


REPLY = """\
comparability: partly comparable | A discusses the state in general, B one country
- similarity: both call the state an instrument of class rule [1, 3]
**difference**: framing | A speaks of a "committee", B of an "organ of oppression" [1] vs [3]
difference: omitted context | B leaves out who elected the assembly [2, 3]
difference: the tone differs [1, 3]
disagreement: A dates the rising to May, B to June [2, 3]
observation: B writes from the standpoint of a party leader [3]
uncertain: whether B's figures come from official records
uncertain: whether B's figures come from official records
Here is some prose the model added.
"""


def test_parse_reads_every_kind_of_line():
    parsed = parse_comparison(REPLY)

    assert parsed.comparability is Comparability.PARTLY
    assert parsed.comparability_note == "A discusses the state in general, B one country"
    kinds = [p.kind for p in parsed.points]
    assert kinds == [
        PointKind.SIMILARITY, PointKind.DIFFERENCE, PointKind.DIFFERENCE,
        PointKind.DIFFERENCE, PointKind.DISAGREEMENT, PointKind.OBSERVATION,
    ]
    framing, omission, unlabelled = parsed.points[1:4]
    assert framing.aspect == "framing"
    assert framing.evidence == (1, 3)
    assert framing.description == 'A speaks of a "committee", B of an "organ of oppression"'

    assert omission.aspect == "omission"
    assert unlabelled.aspect == "" and unlabelled.description == "the tone differs"
    assert parsed.uncertainties == ("whether B's figures come from official records",)


def test_parse_returns_none_for_prose():
    assert parse_comparison("These two texts are quite different.") is None


def test_a_reply_of_only_a_comparability_line_is_valid():
    parsed = parse_comparison("comparability: not comparable | different subjects")
    assert parsed.comparability is Comparability.LOW
    assert parsed.points == ()


def test_check_points_keeps_only_supported_points():
    source_of = {1: "A", 2: "A", 3: "B"}
    points = (
        ComparisonPoint(PointKind.SIMILARITY, "both", (1, 3)),
        ComparisonPoint(PointKind.DIFFERENCE, "only A cited", (1, 2)),
        ComparisonPoint(PointKind.DISAGREEMENT, "cites a passage not compared", (1, 7)),
        ComparisonPoint(PointKind.OBSERVATION, "about A", (2, 7)),
        ComparisonPoint(PointKind.OBSERVATION, "no citation"),
    )
    kept, dropped = check_points(points, source_of)
    assert [(p.description, p.evidence) for p in kept] == [("both", (1, 3)), ("about A", (2,))]
    assert dropped == 3
