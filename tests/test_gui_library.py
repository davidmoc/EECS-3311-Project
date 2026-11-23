"""The library page: finding, reading and annotating texts (F05, F06)."""

from conftest import ScriptedLLM

from praxis.documents import AnnotationType


def library_page(window):
    return window.show_page("Library")


def open_first_text_titled(page, title):
    for row in range(page.text_list.count()):
        item = page.text_list.item(row)
        if item.text().startswith(title):
            page.text_list.setCurrentItem(item)
            page._open_item(item)
            return
    raise AssertionError(f"{title} is not listed")


def test_texts_are_listed_searched_and_filtered_by_topic(gui):
    window, _ = gui(seed=True)
    page = library_page(window)

    assert page.text_list.count() == 14
    page.search_box.setText("Kropotkin bread")
    page.search()
    assert [page.text_list.item(r).text().split("\n")[0] for r in range(page.text_list.count())] == [
        "The Conquest of Bread (1892)",
    ]
    anarchism = page.topic_box.findData("anarchism")
    page.topic_box.setCurrentIndex(anarchism)
    assert page.text_list.count() == 1


def test_the_library_page_is_refreshed_after_the_home_page_loads_texts(gui):
    window, _ = gui()
    assert library_page(window).text_list.count() == 0

    window.show_page("Home").load_button.click()

    assert library_page(window).text_list.count() == 14


def test_only_the_list_shows_until_a_text_is_chosen(gui):
    window, _ = gui(seed=True)
    page = library_page(window)
    assert not page.reading

    open_first_text_titled(page, "The Communist Manifesto")
    assert page.reading
    assert page.title.text() == "The Communist Manifesto — Karl Marx and Friedrich Engels"

    page.back_button.click()
    assert not page.reading


def test_the_whole_text_is_one_scroll_and_reading_records_progress(gui):
    window, application = gui(seed=True)
    window.show()
    page = library_page(window)
    open_first_text_titled(page, "The Communist Manifesto")
    shown = page.reader.toPlainText()
    total = page.text.total

    assert shown.startswith("¶1")
    assert f"¶{total}  " in shown  # the last paragraph too: no pages to turn
    record = application.profiles.get_profile().history.get(page.text.document.id)
    assert record.furthest_paragraph == 1

    page.reader.verticalScrollBar().setValue(page.reader.verticalScrollBar().maximum())
    page.record_progress(page.reader.furthest_visible())

    record = application.profiles.get_profile().history.get(page.text.document.id)
    assert record.furthest_paragraph == total


def test_a_text_opens_at_the_paragraph_asked_for(gui):
    window, application = gui(seed=True)
    window.show()
    page = library_page(window)
    manifesto = next(d for d in application.library.browse() if d.title == "The Communist Manifesto")

    page.open_text(str(manifesto.id), 40)

    assert page.opened_at == 40
    assert page.reader.verticalScrollBar().value() > 0
    assert application.profiles.get_profile().history.get(manifesto.id).furthest_paragraph >= 40


def ask(page, paragraph, annotation_type):
    menu = page.paragraph_menu(paragraph)
    action = next(a for a in menu.actions() if a.data() is annotation_type)
    action.trigger()


def test_a_paragraph_menu_offers_every_annotation_type(gui):
    window, _ = gui(seed=True)
    page = library_page(window)
    open_first_text_titled(page, "The Communist Manifesto")

    labels = [a.text().strip() for a in page.paragraph_menu(3).actions() if a.text()]

    assert labels[0] == "Ask about ¶3"
    assert [a.data() for a in page.paragraph_menu(3).actions() if a.data()] == list(AnnotationType)
    assert labels[-1] == "Save paragraph to workspace"


def test_a_requested_annotation_shows_as_pending_then_inline(gui):
    llm = ScriptedLLM("The passage argues that all history is class struggle.")
    window, application = gui(llm, seed=True)
    page = library_page(window)
    open_first_text_titled(page, "The Communist Manifesto")
    pending = []
    page.reader.textChanged.connect(lambda: pending.append("Asking about the argument of ¶3…" in page.reader.toPlainText()))

    ask(page, 3, AnnotationType.ARGUMENT)

    assert pending[0]  # shown while the request ran
    shown = page.reader.toPlainText()
    assert "Asking about" not in shown
    assert "AI annotation · argument" in shown
    assert shown.index("all history is class struggle") < shown.index("¶4  ")
    assert "(15 model tokens)" in page.message.text()
    assert len(application.annotations.annotations_for(page.text.document)) == 1
    assert "Passage to annotate (¶3)" in llm.prompts[0].user

    page.back_button.click()
    open_first_text_titled(page, "The Communist Manifesto")
    assert "all history is class struggle" in page.reader.toPlainText()  # kept


def test_without_a_model_asking_reports_the_error_under_the_paragraph(gui):
    window, _ = gui(seed=True)
    page = library_page(window)
    open_first_text_titled(page, "The Communist Manifesto")

    ask(page, 2, AnnotationType.TERMINOLOGY)

    shown = page.reader.toPlainText()
    assert "✕ Error:" in shown
    assert shown.index("✕ Error:") < shown.index("¶3  ")
