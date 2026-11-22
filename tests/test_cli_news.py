"""The news commands (F01)."""

from datetime import date, timedelta

import pytest

from praxis import app as app_module
from praxis.cli import commands
from praxis.config import Settings
from praxis.documents import NewsArticle
from praxis.news import NewsProvider, NewsProviderError

TODAY = date.today()


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


def article(title, outlet, day=TODAY):
    return NewsArticle(
        title=title, author="Staff", outlet=outlet, publication_date=day,
        text="Dockworkers walked out over wages and the ports closed.",
        source_url=f"https://example.org/{title.replace(' ', '-')}",
    )


def use_providers(monkeypatch, cli_database, *providers):
    monkeypatch.setattr(
        commands, "application_factory",
        lambda: app_module.build_application(
            Settings(openai_api_key=None), cli_database, news_providers=list(providers)
        ),
    )


def test_refresh_reports_each_outlet_and_unavailable_sources(run, monkeypatch, cli_database):
    use_providers(
        monkeypatch, cli_database,
        StaticProvider("Example Wire", article("Port strike", "Example Wire"), article("Talks stall", "Example Wire")),
        DownProvider(),
    )
    result = run("news", "refresh")
    assert result.exit_code == 0, result.output
    assert "Example Wire: 2 articles" in result.output
    assert "Down Wire: unavailable — timed out" in result.output
    assert "2 articles fetched, 2 new." in result.output
    assert "the news is limited" in result.output


def test_list_shows_stored_headlines_newest_first(run, monkeypatch, cli_database):
    use_providers(
        monkeypatch, cli_database,
        StaticProvider("Example Wire", article("Older", "Example Wire", TODAY - timedelta(days=1)),
                       article("Newer", "Example Wire")),
        StaticProvider("Other Wire", article("Elsewhere", "Other Wire")),
    )
    run("news", "refresh")
    output = run("news", "list").output
    assert output.index("Newer") < output.index("Older")
    assert "Example Wire  https://example.org/Newer" in output

    only = run("news", "list", "--outlet", "other").output
    assert "Elsewhere" in only and "Newer" not in only


def test_list_still_works_when_every_source_is_down(run, monkeypatch, cli_database):
    use_providers(monkeypatch, cli_database, StaticProvider("Example Wire", article("Port strike", "Example Wire")))
    run("news", "refresh")
    use_providers(monkeypatch, cli_database, DownProvider())
    refresh = run("news", "refresh").output
    assert "No news source could be reached" in refresh
    assert "Port strike" in run("news", "list").output


def test_list_when_nothing_is_stored(run):
    assert "praxis news refresh" in run("news", "list").output


def test_news_stays_out_of_library_browse_but_can_be_read(run, monkeypatch, cli_database):
    use_providers(monkeypatch, cli_database, StaticProvider("Example Wire", article("Port strike", "Example Wire")))
    run("news", "refresh")
    assert "The library is empty" in run("library", "browse").output
    short = run("news", "list").output.split()[0]
    read = run("library", "read", short)
    assert read.exit_code == 0, read.output
    assert "Dockworkers walked out" in read.output
