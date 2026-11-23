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


def test_reading_a_page_records_progress_and_pages_turn(gui):
    window, application = gui(seed=True)
    page = library_page(window)
    open_first_text_titled(page, "The Communist Manifesto")

    assert page.title.text() == "The Communist Manifesto — Karl Marx and Friedrich Engels"
    assert page.position.text().startswith("¶1–10 of ")
    assert "¶1" in page.reader.toPlainText()
    assert not page.previous_button.isEnabled() and page.next_button.isEnabled()

    page.next_button.click()

    assert page.position.text().startswith("¶11–20 of ")
    record = application.profiles.get_profile().history.get(page.page.document.id)
    assert record.furthest_paragraph == 20


def test_an_annotation_is_shown_apart_from_the_text_and_kept(gui):
    llm = ScriptedLLM("The passage argues that all history is class struggle.")
    window, application = gui(llm, seed=True)
    page = library_page(window)
    open_first_text_titled(page, "The Communist Manifesto")
    page.paragraph_box.setValue(3)
    page.type_box.setCurrentIndex(page.type_box.findData(AnnotationType.ARGUMENT))

    page.annotate_button.click()

    shown = page.annotation.toPlainText()
    assert "AI annotation: argument" in shown
    assert "all history is class struggle" in shown
    assert "(15 model tokens)" in shown
    assert len(application.annotations.annotations_for(page.page.document)) == 1
    assert "Passage to annotate (¶3)" in llm.prompts[0].user


def test_without_a_model_annotating_reports_the_error(gui):
    window, _ = gui(seed=True)
    page = library_page(window)
    open_first_text_titled(page, "The Communist Manifesto")

    page.annotate_button.click()

    assert page.annotation.toPlainText().startswith("Error:")
    assert page.annotate_button.isEnabled()
