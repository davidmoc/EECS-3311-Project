"""The home page: news to look into, readings to return to, and the
learning path in progress."""

from conftest import ScriptedLLM
from test_gui_news import CARD, Wires
from test_gui_paths import REPLY

from praxis.gui.home import NO_NEWS, NO_PATH, NO_READINGS


def manifesto(application):
    return next(d for d in application.library.browse() if d.title == "The Communist Manifesto")


def test_fetched_news_is_shown_as_cards_that_open_the_event(gui):
    window, _ = gui(ScriptedLLM(CARD, "background terms", "## Account\nThree died."), news=[Wires()])
    home = window.page("Home")

    home.fetch_news()

    assert len(home.news_cards) == 1
    card = home.news_cards[0]
    assert card.title.text() == "Fire at Indonesian candy factory"
    assert "2 outlets · labour" in card.details.text()
    assert card.body.text().startswith("AI summary: Three workers died")
    assert window.page("News").event_list.count() == 1  # handed over, not fetched again

    card.clicked.emit()

    assert window.current_title == "News"
    assert window.page("News").selected is not None


def test_without_news_the_page_says_so(gui):
    window, _ = gui()
    home = window.page("Home")

    home.fetch_news()

    assert home.news_cards == []
    assert home.news_status.text() == NO_NEWS


def test_unfinished_readings_are_offered_and_continue_where_they_stopped(gui):
    window, application = gui(seed=True)
    home = window.page("Home")
    assert home.reading_cards == [] and home.readings_status.text() == NO_READINGS
    text = manifesto(application)
    window.show_page("Library").open_text(str(text.id), 40)

    window.show_page("Home")

    assert len(home.reading_cards) == 1
    card = home.reading_cards[0]
    assert card.title.text() == "The Communist Manifesto"
    assert card.body.text().startswith(f"¶40 of {len(text.passages())}")

    window.page("Library").show_list()
    card.clicked.emit()

    assert window.current_title == "Library"
    assert window.page("Library").reading and window.page("Library").opened_at == 40


def test_finished_texts_are_not_offered(gui):
    window, application = gui(seed=True)
    window.show_page("Library").open_text(str(manifesto(application).id), 10_000)

    assert window.show_page("Home").reading_cards == []


def test_the_learning_path_in_progress_shows_its_next_step(gui):
    window, _ = gui(ScriptedLLM(REPLY), seed=True)
    home = window.page("Home")
    assert home.path_card is None and home.path_status.text() == NO_PATH
    research = window.show_page("Research")
    research.choose("path")
    research.input.setText("historical materialism")
    research.run_button.click()

    window.show_page("Home")

    assert home.path_card.title.text() == "historical materialism"
    assert home.path_card.details.text() == "0 of 2 steps dealt with"
    assert home.path_card.body.text().startswith("Next: step 1 of 2 — Class struggle")
    assert home.continue_button.text() == "Continue"

    home.continue_button.click()  # the step's first reading

    assert window.current_title == "Library"
    assert window.page("Library").reading

    home.path_card.clicked.emit()

    assert window.current_title == "Learning paths"
    assert window.page("Learning paths").path.target == "historical materialism"
