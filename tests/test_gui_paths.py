"""The learning paths page: stored paths and progress (F08)."""

from conftest import ScriptedLLM

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
    assert "Learning path for historical materialism" in shown
    assert "1. Class struggle" in shown and "Read:" in shown
    assert "Orientation (AI-generated; nothing in the library on this)" in shown


def test_marking_a_step_done_updates_the_path_and_the_reader_model(gui):
    window, application, path = built_path(gui)
    page = window.show_page("Learning paths")
    page.open_path(path.id)
    page.step_box.setValue(1)
    page.status_box.setCurrentIndex(page.status_box.findData(StepStatus.DONE))

    page.mark_button.click()

    assert "Your reader model now counts you as knowing Class struggle" in page.message.text()
    assert "✓ done" in page.output.toPlainText()
    assert page.path_list.item(0).text().endswith("1/2 steps")
    level = application.profiles.get_profile().knowledge.get_level("class struggle")
    assert level is KnowledgeLevel.INTRODUCTORY


def test_skipping_leaves_the_reader_model_alone(gui):
    window, application, path = built_path(gui)
    page = window.show_page("Learning paths")
    page.open_path(path.id)
    page.step_box.setValue(2)
    page.status_box.setCurrentIndex(page.status_box.findData(StepStatus.SKIPPED))

    page.mark_button.click()

    assert page.message.text() == "Step 2 (Phrenology): skipped."
    assert application.profiles.get_profile().knowledge.get_level("phrenology") is KnowledgeLevel.NONE


def test_with_no_paths_the_page_says_where_to_build_one(gui):
    window, _ = gui()
    page = window.show_page("Learning paths")

    assert "Build one on the Research page" in page.output.toPlainText()
    assert not page.mark_button.isEnabled()
