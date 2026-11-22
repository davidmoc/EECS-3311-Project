"""NewsService.get_dashboard_events and stored events (F01, SD03)."""

from datetime import date

import pytest
from conftest import ScriptedLLM

from praxis.documents import NewsArticle
from praxis.news import NewsProvider, NewsProviderError
from praxis.news.events import Grouping, SummaryStatus
from praxis.news.service import LIMITED_NEWS, NO_MODEL, NO_NEWS_REACHED, NewsError, NewsService
from praxis.news.summary import NewsSummaryService
from praxis.persistence import Database, SQLDocumentRepository
from praxis.persistence.events import SQLEventRepository

TODAY = date(2026, 11, 22)


def report(title, outlet, text):
    return NewsArticle(title=title, author="Staff", outlet=outlet, text=text, publication_date=TODAY,
                       source_url=f"https://{outlet.replace(' ', '')}.example/{title.replace(' ', '-')}")


FIRE_A = report("Fire at Indonesian candy factory kills three", "Wire A", "A fire at a candy factory in Indonesia killed three workers.")
FIRE_B = report("Indonesian candy factory fire leaves dozens missing", "Wire B", "Dozens of workers are missing after a candy factory fire in Indonesia.")
LONE = report("Liverpool thrash United", "Wire C", "A football report.")

CARD = (
    "title: Fire at Indonesian candy factory\n"
    "summary: Three workers died [1] and dozens are missing [2].\n"
    "category: labour\nsame event: yes"
)


class StaticProvider(NewsProvider):
    def __init__(self, name, *articles):
        self.name = name
        self.articles = articles

    def get_recent_news(self):
        return list(self.articles)


class DownProvider(NewsProvider):
    name = "Down Wire"

    def get_recent_news(self):
        raise NewsProviderError("timed out")


@pytest.fixture
def database():
    database = Database()
    yield database
    database.close()


def news_service(database, llm, *providers):
    documents = SQLDocumentRepository(database)
    return NewsService(
        list(providers) or [StaticProvider("Wire", FIRE_A, FIRE_B, LONE)],
        documents,
        today=lambda: TODAY,
        summaries=NewsSummaryService(llm),
        events=SQLEventRepository(database, documents),
    )


def test_dashboard_groups_summarises_and_ranks_events(database):
    llm = ScriptedLLM(CARD)
    dashboard = news_service(database, llm).get_dashboard_events()

    assert dashboard.total_events == 2
    fire, lone = dashboard.events
    assert fire.headline == "Fire at Indonesian candy factory"
    assert fire.summary_status is SummaryStatus.SUMMARIZED
    assert fire.categories == ("labour",)
    # A single report is shown as it is, without a model call.
    assert lone.grouping is Grouping.SINGLE_REPORT
    assert lone.summary_status is SummaryStatus.NOT_SUMMARIZED
    assert len(llm.prompts) == 1
    assert dashboard.tokens_used == 15
    assert dashboard.warnings == ()


def test_a_stored_summary_is_reused_while_the_reports_are_the_same(database):
    news_service(database, ScriptedLLM(CARD)).get_dashboard_events()
    llm = ScriptedLLM()  # any model call would fail: no replies
    dashboard = news_service(database, llm).get_dashboard_events()
    assert dashboard.events[0].summary.startswith("Three workers died")
    assert llm.prompts == []


def test_limit_caps_the_events_shown(database):
    dashboard = news_service(database, ScriptedLLM(CARD)).get_dashboard_events(limit=1)
    assert len(dashboard.events) == 1
    assert dashboard.total_events == 2


def test_an_unavailable_source_limits_the_dashboard(database):
    service = news_service(database, ScriptedLLM(CARD), StaticProvider("Wire", FIRE_A, FIRE_B), DownProvider())
    dashboard = service.get_dashboard_events()
    assert LIMITED_NEWS.format(outlets="Down Wire") in dashboard.warnings
    assert dashboard.events


def test_with_every_source_down_stored_news_is_shown(database):
    news_service(database, ScriptedLLM(CARD)).get_dashboard_events()
    dashboard = news_service(database, ScriptedLLM(), DownProvider()).get_dashboard_events()
    assert NO_NEWS_REACHED in dashboard.warnings
    assert dashboard.events[0].is_summarized  # reused from the first run


def test_without_a_model_events_show_headlines(database):
    dashboard = news_service(database, None).get_dashboard_events()
    assert NO_MODEL in dashboard.warnings
    assert dashboard.events[0].summary_status is SummaryStatus.HEADLINES_ONLY


def test_dashboard_can_be_built_from_stored_news_only(database):
    news_service(database, ScriptedLLM(CARD)).refresh()
    provider = StaticProvider("Wire")
    service = news_service(database, ScriptedLLM(CARD), provider)
    provider.get_recent_news = lambda: pytest.fail("should not fetch")
    assert service.get_dashboard_events(refresh=False).refresh is None


def test_events_can_be_found_and_reopened(database):
    service = news_service(database, ScriptedLLM(CARD))
    fire = service.get_dashboard_events().events[0]
    found = service.find_event(str(fire.id)[:8])
    assert service.get_event(found) == fire


def test_unknown_events_are_reported(database):
    service = news_service(database, None)
    with pytest.raises(NewsError, match="No event"):
        service.find_event("abcd")


def test_an_event_can_be_opened_in_its_expanded_view(database):
    service = news_service(database, ScriptedLLM(CARD))
    fire = service.get_dashboard_events().events[0]
    expanded = service.get_expanded_event(fire.id)
    assert expanded.event == fire
    assert [s.citation.document_title for s in expanded.report_sources] == [r.title for r in fire.reports]
