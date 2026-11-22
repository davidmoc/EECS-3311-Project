"""SQLComparisonRepository (F10)."""

from datetime import date, datetime, timedelta, timezone

import pytest

from praxis.agent import ResearchCorpus
from praxis.comparison import Comparability, ComparisonPoint, PointKind, SourceComparison, SourceProfile
from praxis.documents import Book, NewsArticle
from praxis.persistence import Database
from praxis.persistence.comparisons import SQLComparisonRepository


@pytest.fixture
def repository():
    database = Database()
    yield SQLComparisonRepository(database)
    database.close()


def a_comparison(subject="the peasantry", created_at=None):
    book = Book(title="Brumaire", author="Marx", text="The allotment farmers.", license="Public Domain",
                publication_date=date(1852, 1, 1))
    news = NewsArticle(title="Farm protest", author="Staff", outlet="Example Wire",
                       text="Farmers blocked the roads.", source_url="https://example.org/f")
    corpus = ResearchCorpus()
    for document in (book, news):
        corpus.add_passage(document, document.passages()[0])
    return SourceComparison(
        subject,
        (SourceProfile.of(book), SourceProfile.of(news)),
        tuple(corpus.sources),
        points=(
            ComparisonPoint(PointKind.DIFFERENCE, "allotment vs farmer", (1, 2), "terminology"),
            ComparisonPoint(PointKind.OBSERVATION, "the wire writes for markets", (2,)),
        ),
        comparability=Comparability.PARTLY,
        comparability_note="a century apart",
        uncertainties=("which farmers",),
        warnings=("1 point was left out.",),
        personalized=True,
        tokens_used=123,
        **({"created_at": created_at} if created_at else {}),
    )


def test_a_stored_comparison_comes_back_whole(repository):
    comparison = a_comparison()
    repository.save(comparison)
    restored = repository.get(comparison.id)
    assert restored == comparison
    assert restored.source_of(2).outlet == "Example Wire"
    assert restored.passages[0].citation.quoted_text == "The allotment farmers."


def test_missing_comparison_is_none(repository):
    assert repository.get(a_comparison().id) is None


def test_list_is_newest_first_with_titles(repository):
    now = datetime.now(timezone.utc)
    older = a_comparison("older", now - timedelta(hours=1))
    newer = a_comparison("newer", now)
    repository.save(older)
    repository.save(newer)
    summaries = repository.list_recent()
    assert [s.subject for s in summaries] == ["newer", "older"]
    assert summaries[0].titles == ("Brumaire", "Farm protest")
    assert summaries[0].comparability is Comparability.PARTLY
    assert len(repository.list_recent(limit=1)) == 1


def test_find_ids_by_prefix(repository):
    comparison = a_comparison()
    repository.save(comparison)
    assert repository.find_ids(str(comparison.id)[:6]) == [comparison.id]
    assert repository.find_ids("%") == []
    assert repository.find_ids("") == []
