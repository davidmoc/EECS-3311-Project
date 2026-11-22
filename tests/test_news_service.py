"""NewsService and keeping news out of the reading library (F01)."""

from datetime import date

import pytest

from praxis.documents import Book, NewsArticle
from praxis.library import LibraryService
from praxis.news import NewsProvider, NewsProviderError
from praxis.news.service import NewsService
from praxis.persistence import Database, SQLDocumentRepository

TODAY = date(2026, 11, 22)


class StaticProvider(NewsProvider):
    def __init__(self, name, *articles):
        self.name = name
        self.articles = list(articles)

    def get_recent_news(self):
        return list(self.articles)


class DownProvider(NewsProvider):
    name = "Down Wire"

    def get_recent_news(self):
        raise NewsProviderError("Could not download https://down.example: timed out")


def article(title, day, outlet="Example Wire", text="Workers at the port struck for higher wages today."):
    return NewsArticle(
        title=title, author="Staff", outlet=outlet, text=text,
        publication_date=day, source_url=f"https://example.org/{title.replace(' ', '-')}",
    )


@pytest.fixture
def documents():
    database = Database()
    yield SQLDocumentRepository(database)
    database.close()


def service(documents, *providers):
    return NewsService(list(providers), documents, today=lambda: TODAY)


def test_refresh_stores_articles_from_every_source(documents):
    a = article("Port strike", TODAY)
    b = article("Talks stall", TODAY, outlet="Other Wire")
    refresh = service(documents, StaticProvider("Example Wire", a), StaticProvider("Other Wire", b)).refresh()

    assert {x.title for x in refresh.fetched} == {"Port strike", "Talks stall"}
    assert refresh.new_count == 2
    assert not refresh.failures
    assert documents.find_by_id(a.id).outlet == "Example Wire"


def test_refreshing_again_updates_without_counting_articles_as_new(documents):
    news = service(documents, StaticProvider("Example Wire", article("Port strike", TODAY)))
    news.refresh()
    assert news.refresh().new_count == 0
    assert documents.count("news") == 1


def test_one_source_down_does_not_stop_the_others(documents):
    refresh = service(documents, DownProvider(), StaticProvider("Example Wire", article("Port strike", TODAY))).refresh()
    assert len(refresh.fetched) == 1
    assert refresh.failures == (("Down Wire", "Could not download https://down.example: timed out"),)
    assert refresh.is_limited and not refresh.all_failed


def test_every_source_down(documents):
    refresh = service(documents, DownProvider()).refresh()
    assert refresh.all_failed and not refresh.is_limited


def test_recent_news_is_newest_first_within_the_window(documents):
    old = article("Old story", date(2026, 11, 1))
    yesterday = article("Yesterday", date(2026, 11, 21))
    today = article("Today", TODAY)
    undated = article("Undated", None)
    for a in (old, yesterday, today, undated):
        documents.save(a)

    titles = [a.title for a in service(documents).get_recent_news(days=2)]

    assert titles == ["Today", "Yesterday"]
    # Stored news is still there when no source can be reached.
    assert [a.title for a in service(documents, DownProvider()).get_recent_news(days=30)] == [
        "Today", "Yesterday", "Old story",
    ]


def test_news_is_kept_out_of_the_reading_library(documents):
    documents.save(Book(title="Manifesto", author="Marx", text="Workers of the world unite.", topics=("class",)))
    documents.save(article("Port strike", TODAY, text="Workers struck at the port."))
    library = LibraryService(documents)

    assert [d.title for d in library.browse()] == ["Manifesto"]
    assert [d.title for d in library.search("workers")] == ["Manifesto"]
    assert library.topics() == [("class", 1)]


def test_a_library_holding_only_news_counts_as_empty(documents):
    documents.save(article("Port strike", TODAY))
    assert LibraryService(documents).is_empty()


def test_news_passages_can_still_be_searched(documents):
    """Questions, research and comparisons may draw on stored news."""
    documents.save(article("Port strike", TODAY))
    matches = documents.search_passages("port strike wages")
    assert [m.document.title for m in matches] == ["Port strike"]
