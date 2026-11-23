"""The learning paths page: stored paths and progress (F08)."""

from conftest import ScriptedLLM
from PySide6.QtCore import QUrl

from praxis.reader_model import KnowledgeLevel
from praxis.reading import StepStatus

REPLY = """\
prerequisite: Class struggle | concept | essential
search: class struggles, freeman and slave
why: The target reads history as class conflict.
orientation: History moves through conflicts between classes.

prerequisite: Phrenology | theory | helpful
search: phrenology
why: The method answers it.
orientation: A 19th-century pseudo-science reading character from the skull.
"""


def built_path(gui):
    window, application = gui(ScriptedLLM(REPLY), seed=True)
    research = window.show_page("Research")
    research.choose("path")
    research.input.setText("historical materialism")
    research.run_button.click()
    return window, application, research.result


def test_a_built_path_is_listed_and_shown(gui):
    window, _, path = built_path(gui)
    page = window.show_page("Learning paths")

    assert page.path_list.count() == 1
    assert page.path_list.item(0).text() == "historical materialism\n0/2 steps"
    page.open_path(path.id)
    shown = page.output.toPlainText()
    assert "Learning path: historical materialism" in shown
    assert "0 of 2 steps dealt with" in shown and "Next: step 1, Class struggle" in shown
    assert "1. Class struggle" in shown and "Read:" in shown
    assert "AI-GENERATED  Orientation — nothing in the library on this" in shown
    assert "✓ Mark done" in shown and "I already know this" in shown


def test_marking_a_step_done_updates_the_path_and_the_reader_model(gui):
    window, application, path = built_path(gui)
    page = window.show_page("Learning paths")
    page.open_path(path.id)

    page.output.anchorClicked.emit(QUrl("praxis:step/1/done"))  # the step's "Mark done"

    assert "Your reader model now counts you as knowing Class struggle" in page.message.text()
    shown = page.output.toPlainText()
    assert "✓ DONE" in shown and "1 of 2 steps dealt with" in shown and "Undo" in shown
    assert page.path_list.item(0).text().endswith("1/2 steps")
    level = application.profiles.get_profile().knowledge.get_level("class struggle")
    assert level is KnowledgeLevel.INTRODUCTORY


def test_skipping_leaves_the_reader_model_alone(gui):
    window, application, path = built_path(gui)
    page = window.show_page("Learning paths")
    page.open_path(path.id)

    page.output.anchorClicked.emit(QUrl("praxis:step/2/skipped"))

    assert page.message.text() == "Step 2 (Phrenology): skipped."
    assert application.profiles.get_profile().knowledge.get_level("phrenology") is KnowledgeLevel.NONE


def test_with_no_paths_the_page_says_where_to_build_one(gui):
    window, _ = gui()
    page = window.show_page("Learning paths")

    assert "Build one on the Research page" in page.output.toPlainText()


def test_undo_puts_a_step_back_to_do(gui):
    window, _, path = built_path(gui)
    page = window.show_page("Learning paths")
    page.open_path(path.id)
    page.mark(1, StepStatus.DONE)

    page.output.anchorClicked.emit(QUrl("praxis:step/1/todo"))

    assert page.path.steps[0].status is StepStatus.TODO
    assert page.path_list.item(0).text().endswith("0/2 steps")


def test_a_path_built_on_the_research_page_links_to_its_page(gui):
    window, _, path = built_path(gui)
    research = window.page("Research")
    assert "Track your progress on the Learning paths page" in research.output.toPlainText()

    research.output.anchorClicked.emit(QUrl(f"praxis:path/{path.id}"))

    assert window.current_title == "Learning paths"
    assert window.page("Learning paths").path.id == path.id
