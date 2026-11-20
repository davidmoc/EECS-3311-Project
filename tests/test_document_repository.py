from datetime import date
from uuid import uuid4

import pytest

from praxis.documents import Article, Book, NewsArticle
from praxis.persistence import Database, SQLDocumentRepository


@pytest.fixture
def repository():
    database = Database()
    yield SQLDocumentRepository(database)
    database.close()


def capital():
    return Book(
        title="Capital, Volume I",
        author="Karl Marx",
        text="The wealth of those societies in which the capitalist mode of "
        "production prevails...\n\nA commodity is an object outside us.",
        publication_date=date(1867, 9, 14),
        source_url="https://example.org/capital",
        license="Public Domain",
        downloadable=True,
        topics=("political economy", "commodity"),
    )


def imperialism():
    return Book(
        title="Imperialism, the Highest Stage of Capitalism",
        author="V. I. Lenin",
        text="Monopoly and finance capital.",
        topics=("imperialism",),
    )


def test_saved_document_round_trips_with_all_fields(repository):
    original = capital()
    repository.save(original)

    loaded = repository.find_by_id(original.id)

    assert loaded == original
    assert isinstance(loaded, Book)
    assert [p.id for p in loaded.passages()] == [p.id for p in original.passages()]


def test_subclass_and_its_fields_survive_storage(repository):
    news = NewsArticle(title="Strike begins", author="Staff", outlet="Wire Service")
    repository.save(news)

    loaded = repository.find_by_id(news.id)

    assert isinstance(loaded, NewsArticle)
    assert loaded.outlet == "Wire Service"
    assert loaded.publication_date is None


def test_unknown_id_returns_none(repository):
    assert repository.find_by_id(uuid4()) is None


def test_saving_again_replaces_rather_than_duplicates(repository):
    book = capital()
    repository.save(book)
    book.title = "Capital: A Critique of Political Economy"
    repository.save(book)

    assert [d.title for d in repository.search("capital")] == [
        "Capital: A Critique of Political Economy"
    ]


def test_search_covers_title_author_topics_and_text(repository):
    repository.save(capital())
    repository.save(imperialism())

    assert [d.author for d in repository.search("lenin")] == ["V. I. Lenin"]
    assert [d.author for d in repository.search("COMMODITY")] == ["Karl Marx"]
    assert [d.author for d in repository.search("finance")] == ["V. I. Lenin"]


def test_every_term_must_match(repository):
    repository.save(capital())
    repository.save(imperialism())

    assert [d.author for d in repository.search("capital marx")] == ["Karl Marx"]
    assert repository.search("capital anarchism") == []


def test_title_matches_rank_above_text_only_matches(repository):
    repository.save(
        Article(title="Notes on the state", author="X", text="about imperialism")
    )
    repository.save(imperialism())

    assert [d.author for d in repository.search("imperialism")] == [
        "V. I. Lenin",
        "X",
    ]


def test_blank_query_returns_nothing(repository):
    repository.save(capital())

    assert repository.search("   ") == []


def test_like_wildcards_in_query_are_literal(repository):
    repository.save(capital())
    repository.save(Article(title="100% of surplus", author="Y"))

    assert [d.author for d in repository.search("%")] == ["Y"]
    assert repository.search("_") == []


def test_data_persists_across_connections(tmp_path):
    path = tmp_path / "nested" / "library.db"
    first = Database(path)
    book = capital()
    SQLDocumentRepository(first).save(book)
    first.close()

    second = Database(path)
    assert SQLDocumentRepository(second).find_by_id(book.id) == book
    second.close()


def test_list_all_returns_every_document_by_title(repository):
    repository.save(imperialism())
    repository.save(capital())

    assert [d.title for d in repository.list_all()] == [
        "Capital, Volume I",
        "Imperialism, the Highest Stage of Capitalism",
    ]


def test_ids_by_prefix_reads_ids_only_and_ignores_case(repository):
    first, second = capital(), imperialism()
    repository.save(first)
    repository.save(second)

    assert repository.find_ids_by_prefix(str(first.id)[:8].upper()) == [first.id]
    assert set(repository.find_ids_by_prefix("")) == {first.id, second.id}
    assert repository.find_ids_by_prefix("%") == []
    assert repository.find_ids_by_prefix("zz") == []


def test_count(repository):
    assert repository.count() == 0
    repository.save(capital())
    assert repository.count() == 1
