"""The news page: the dashboard and an event's view (F01, F02, F15)."""

from datetime import date

from conftest import ScriptedLLM

from praxis.documents import NewsArticle
from praxis.gui.news import EMPTY
from praxis.news import NewsProvider

TODAY = date.today()
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


class Wires(NewsProvider):
    name = "Wires"

    def get_recent_news(self):
        return list(FIRE)


def news_page(gui, *replies):
    window, application = gui(ScriptedLLM(*replies) if replies else None, news=[Wires()])
    return window, application, window.show_page("News")


def test_fetching_shows_event_cards_with_their_ai_summary(gui):
    window, _, page = news_page(gui, CARD)

    page.fetch_button.click()

    assert page.event_list.count() == 1
    card = page.event_list.item(0).text()
    assert card.startswith("Fire at Indonesian candy factory\n")
    assert "labour · 2 outlets: Wire A, Wire B" in card
    assert "Summary (AI-generated from the reports): Three workers died [1]" in card
    assert page.message.text().startswith("The 1 most widely reported of 1 events (2 reports).")


def test_with_nothing_stored_the_page_says_to_fetch(gui):
    window, _ = gui()
    page = window.show_page("News")

    page.show_button.click()

    assert page.event_list.count() == 0
    assert page.message.text().startswith(EMPTY)
    assert not page.save_button.isEnabled()


def test_an_opened_event_shows_its_reports_and_can_be_saved(gui):
    window, application, page = news_page(gui, CARD, "factory fire workers", "Three workers died in the fire [1]; dozens are missing [2].")
    page.fetch_button.click()
    event_id = page.dashboard.events[0].id

    page.event_list.itemClicked.emit(page.event_list.item(0))

    shown = page.output.toPlainText()
    assert shown.startswith("Fire at Indonesian candy factory")
    assert "Wire A, " in shown and "Dozens of workers are missing" in shown
    assert "Account of the event (AI-generated)" in shown
    assert page.selected == event_id and page.save_button.isEnabled()

    page.save_button.click()

    assert page.message.text() == "Saved to your workspace: Event: Fire at Indonesian candy factory"
    assert [i.title for i in application.workspace.get_workspace().items] == ["Event: Fire at Indonesian candy factory"]
