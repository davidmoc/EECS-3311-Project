"""The news commands (F01)."""

import re
from datetime import date, timedelta

import pytest
from conftest import ScriptedLLM

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


# --- the dashboard -----------------------------------------------------------------

FIRE = (
    NewsArticle(title="Fire at Indonesian candy factory kills three", author="Staff", outlet="Wire A",
                publication_date=TODAY, text="A fire at a candy factory in Indonesia killed three workers.",
                source_url="https://a.example/fire"),
    NewsArticle(title="Indonesian candy factory fire leaves dozens missing", author="Staff", outlet="Wire B",
                publication_date=TODAY, text="Dozens of workers are missing after a candy factory fire in Indonesia.",
                source_url="https://b.example/fire"),
)
CARD = (
    "title: Fire at Indonesian candy factory\n"
    "summary: Three workers died [1] and dozens are missing [2].\n"
    "category: labour\nsame event: yes"
)


def use_news(monkeypatch, cli_database, llm, *providers):
    monkeypatch.setattr(
        commands, "application_factory",
        lambda: app_module.build_application(
            Settings(openai_api_key=None), cli_database, llm, news_providers=list(providers)
        ),
    )


def test_dashboard_shows_event_cards(run, monkeypatch, cli_database):
    use_news(
        monkeypatch, cli_database, ScriptedLLM(CARD),
        StaticProvider("Wires", *FIRE, article("Liverpool thrash United", "Wire C")),
    )
    result = run("news", "dashboard")
    assert result.exit_code == 0, result.output
    out = result.output
    assert "News dashboard: the 2 most widely reported of 2 events (3 reports)" in out
    assert re.search(r"1\. Fire at Indonesian candy factory  \[[0-9a-f]{8}\]", out)
    assert "labour · 2 outlets: Wire A, Wire B" in out
    assert "Summary (AI-generated from the reports): Three workers died [1]" in out
    # Live run: report lines lost their indent.
    assert re.search(r"^   \[1\] Wire A: Fire at Indonesian candy factory kills three \([0-9a-f]{8}\)$", out, re.MULTILINE)
    assert "2. Liverpool thrash United" in out
    assert "Single report: no other outlet in the feeds has reported it." in out
    assert "Wire C writes: Dockworkers walked out" in out
    assert "(15 model tokens)" in out


def test_dashboard_without_a_model_shows_headlines(run, monkeypatch, cli_database):
    use_news(monkeypatch, cli_database, None, StaticProvider("Wires", *FIRE))
    out = run("news", "dashboard").output
    assert "No language model is configured" in out
    assert "No summary is shown; read the reports:" in out
    assert "Summary (AI-generated" not in out


def test_offline_dashboard_uses_stored_news(run, monkeypatch, cli_database):
    use_news(monkeypatch, cli_database, ScriptedLLM(CARD), StaticProvider("Wires", *FIRE))
    run("news", "dashboard")
    use_news(monkeypatch, cli_database, ScriptedLLM(), DownProvider())
    out = run("news", "dashboard", "--offline").output
    assert "Fire at Indonesian candy factory" in out
    assert "No news source could be reached" not in out  # nothing was fetched


def test_empty_dashboard(run, monkeypatch, cli_database):
    use_news(monkeypatch, cli_database, None)
    assert "No current news is stored" in run("news", "dashboard", "--offline").output


# --- opening an event (F02) ---------------------------------------------------------

ACCOUNT = (
    "## What happened\nThree workers died [1] and dozens are missing [2].\n\n"
    "## Where the reports differ\nThey do not differ [1, 2].\n\n"
    "## Background from the library\nNone of the passages bears on it.\n\n"
    "## Open questions\n- What caused the fire?\n"
)


def event_id_from(output):
    return re.search(r"1\. .*  \[([0-9a-f]{8})\]", output).group(1)


def test_event_shows_reports_account_and_next_steps(run, monkeypatch, cli_database):
    use_news(monkeypatch, cli_database, ScriptedLLM(CARD, "fire, factory", ACCOUNT), StaticProvider("Wires", *FIRE))
    short = event_id_from(run("news", "dashboard").output)

    result = run("news", "event", short, "--save", "-t", "fire")

    assert result.exit_code == 0, result.output
    out = result.output
    assert f"Fire at Indonesian candy factory  [{short}]" in out
    assert "Still developing: the reports are recent and may change." in out
    assert "[1] Wire A, " in out and "https://a.example/fire" in out
    assert "Account of the event (AI-generated)" in out
    assert "What happened" in out and "Three workers died [1]" in out
    assert "- What caused the fire?" in out
    assert f"Research it:   praxis news event {short} --research" in out
    assert f"Compare outlets: praxis news event {short} --compare" in out
    assert "Saved to your workspace" in out
    # Reports come before the AI account.
    assert out.index("[2] Wire B") < out.index("Account of the event")

    items = run("workspace", "list", "--kind", "event").output
    item = re.search(r"^([0-9a-f]{8})  \[event\] Event: Fire at Indonesian", items, re.MULTILINE).group(1)
    assert f"→ praxis news event {short}" in run("workspace", "open", item).output


def test_event_compare_compares_the_outlets(run, monkeypatch, cli_database):
    use_news(
        monkeypatch, cli_database,
        ScriptedLLM(CARD, "comparability: comparable | same fire\nsimilarity: both report deaths [1, 2]"),
        StaticProvider("Wires", *FIRE),
    )
    short = event_id_from(run("news", "dashboard").output)
    out = run("news", "event", short, "--compare").output
    assert "Comparing on: Fire at Indonesian candy factory" in out
    assert "Source A: Staff, “Fire at Indonesian candy factory kills three” (news, published by Wire A" in out
    assert "both report deaths [1, 2] (sources A, B)" in out


def test_event_research_starts_from_the_reports(run, monkeypatch, cli_database):
    use_news(
        monkeypatch, cli_database,
        ScriptedLLM(CARD, "evidence: factory workers", "verdict: sufficient", "## Findings\nThree died [1]."),
        StaticProvider("Wires", *FIRE),
    )
    short = event_id_from(run("news", "dashboard").output)
    out = run("news", "event", short, "--research").output
    assert "Researching: Fire at Indonesian candy factory" in out
    assert "1. ✓ Start from the event's 2 news reports  +2 sources" in out
    assert "Research session " in out


def test_unknown_event_is_an_error(run):
    result = run("news", "event", "abcdef12")
    assert result.exit_code == 1
    assert "No event with id starting 'abcdef12'" in result.output
