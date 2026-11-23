"""The compare page: two to four texts on one subject (F10)."""

from PySide6.QtCore import Qt
from conftest import ScriptedLLM


def tick(page, *titles):
    for row in range(page.text_list.count()):
        item = page.text_list.item(row)
        if item.text().split(" — ")[0] in titles:
            item.setCheckState(Qt.CheckState.Checked)


def test_two_texts_are_compared_and_the_comparison_is_kept(gui):
    llm = ScriptedLLM(
        "bourgeoisie, revolution",
        "comparability: comparable | Both discuss the bourgeoisie in revolution.\n"
        "similarity: Both treat the bourgeoisie as a revolutionary class [1, 4].",
    )
    window, application = gui(llm, seed=True)
    page = window.show_page("Compare")
    tick(page, "The Communist Manifesto", "The Eighteenth Brumaire of Louis Bonaparte")
    page.subject.setText("the bourgeoisie")

    page.compare_button.click()

    shown = page.output.toPlainText()
    assert shown.startswith("Comparing on: the bourgeoisie")
    assert "Source A: Karl Marx and Friedrich Engels, “The Communist Manifesto”" in shown
    assert "Comparability (AI-assessed): comparable" in shown
    assert "Shared ground" in shown and " A   B  Both treat the bourgeoisie" in shown
    assert page.history.count() == 1
    # Ticks survive the refresh after comparing.
    assert len(page.chosen()) == 2

    page.output.clear()
    page.open_comparison(application.agent.list_comparisons()[0].id)
    assert page.output.toPlainText().startswith("Comparing on: the bourgeoisie")


def test_one_text_is_not_enough(gui):
    window, _ = gui(seed=True)
    page = window.show_page("Compare")
    tick(page, "The Communist Manifesto")
    page.subject.setText("the bourgeoisie")

    page.compare_button.click()

    assert page.message.text() == "Error: Choose at least two different sources to compare."
