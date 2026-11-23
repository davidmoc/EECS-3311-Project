"""The workspace page and saving from other pages (F15, UC15)."""

from PySide6.QtCore import Qt
from conftest import ScriptedLLM

from praxis.workspace import SavedItemKind


def manifesto_page(window, application, start=1):
    library = window.show_page("Library")
    manifesto = next(d for d in application.library.browse() if d.title == "The Communist Manifesto")
    library.open_text(str(manifesto.id), start)
    return library, manifesto


def workspace(window):
    return window.show_page("Workspace")


def open_row(page, row):
    page.open_item(page.item_list.item(row).data(Qt.ItemDataRole.UserRole))


def test_a_saved_paragraph_continues_at_that_paragraph(gui):
    window, application = gui(seed=True)
    library, manifesto = manifesto_page(window, application, 11)
    library.paragraph_menu(13).actions()[-1].trigger()  # "Save paragraph to workspace"

    assert library.message.text().startswith("Saved to your workspace: Karl Marx and Friedrich Engels")
    page = workspace(window)
    assert page.item_list.count() == 1
    open_row(page, 0)
    assert "The history of all hitherto existing societies" in page.output.toPlainText()
    assert page.continue_button.text() == "Continue reading"

    page.continue_button.click()

    assert window.current_title == "Library"
    assert library.opened_at == 13


def test_a_saved_text_continues_where_reading_stopped(gui):
    window, application = gui(seed=True)
    library, _ = manifesto_page(window, application, 30)  # read to ¶30
    library.save_text_button.click()
    page = workspace(window)
    open_row(page, 0)

    page.continue_button.click()

    assert library.opened_at == 31


def test_research_is_saved_and_continued_on_the_past_research_page(gui):
    llm = ScriptedLLM("evidence: barricades Vienna", "verdict: sufficient", "## Findings\nThey fought [1].")
    window, application = gui(llm, seed=True)
    research = window.show_page("Research")
    research.choose("research")
    research.input.setText("Why did Vienna fall?")
    assert not research.save_button.isEnabled()
    research.run_button.click()
    research.save_button.click()
    assert research.message.text().startswith("Saved to your workspace")

    page = workspace(window)
    page.kind_box.setCurrentIndex(page.kind_box.findData(SavedItemKind.RESEARCH))
    assert page.item_list.count() == 1
    open_row(page, 0)
    assert page.continue_button.text() == "Open the research"
    page.continue_button.click()

    assert window.current_title == "Past research"
    assert window.page("Past research").selected == research.result.session.id


def test_notes_are_added_searched_and_removed(gui):
    window, _ = gui()
    page = workspace(window)
    assert page.output.toPlainText() == "Nothing saved yet."

    page.note_button.click()
    assert page.message.text() == "Error: Give the note a title."
    page.note_title.setText("Questions on Bonapartism")
    page.note_text.setPlainText("Why did the peasants vote for him?")
    page.note_button.click()
    page.search_box.setText("peasants")

    assert page.item_list.count() == 1
    open_row(page, 0)
    assert not page.continue_button.isEnabled()
    page.remove_button.click()
    assert page.message.text() == "Removed: Questions on Bonapartism"
    assert page.item_list.count() == 0
