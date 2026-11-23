"""The research page: the agent's requests from the GUI (F03, F04, F07–F09, F11, F12, F14)."""

import pytest
from conftest import ScriptedLLM

from praxis.reader_model import ExplanationDepth


def research_page(window):
    return window.show_page("Research")


def run(page, mode, text):
    page.choose(mode)
    page.input.setText(text)
    page.run_button.click()
    return page.output.toPlainText()


def test_each_mode_shows_only_its_options(gui):
    window, _ = gui()
    page = research_page(window)

    page.choose("analyze")
    assert not page.framework.isHidden() and page.broad.isHidden() and page.detail_box.isHidden()
    page.choose("history")
    assert page.framework.isHidden() and not page.broad.isHidden()
    page.choose("ask")
    assert not page.detail_box.isHidden() and not page.general.isHidden()
    page.choose("path")
    assert page.general.isHidden()


def test_a_question_without_a_model_still_shows_its_passages(gui):
    window, _ = gui(seed=True)
    page = research_page(window)

    shown = run(page, "ask", "Why are wages so low?")

    assert "Why are wages so low?" in shown
    assert "PASSAGES" in shown and "Open in the library ›" in shown
    assert "No language model is configured" in shown


def test_a_question_with_less_detail_is_explained_for_this_request(gui):
    llm = ScriptedLLM("minimum wage", "Wages are the cost of keeping the worker alive [1].")
    window, application = gui(llm, seed=True)
    page = research_page(window)
    page.choose("ask")
    page.detail_box.setCurrentIndex(page.detail_box.findData(ExplanationDepth.BRIEF))

    shown = run(page, "ask", "Why are wages so low?")

    assert "AI-GENERATED  Explanation" in shown
    assert "Wages are the cost of keeping the worker alive" in shown
    assert "two or three sentences" in llm.prompts[1].system
    assert application.profiles.get_profile().explanation_depth is ExplanationDepth.STANDARD


def test_research_shows_its_steps_sources_and_analysis(gui):
    llm = ScriptedLLM(
        "evidence: barricades Vienna workers", "verdict: sufficient",
        "## Findings\nThe workers fought alone [1].\n\n## Open questions\n- Why did the peasants stay home?",
    )
    window, _ = gui(llm, seed=True)

    shown = run(research_page(window), "research", "Why did the Vienna insurrection fail?")

    assert "HOW IT WAS RESEARCHED" in shown and "✓" in shown
    assert "AI-GENERATED  Analysis" in shown
    assert "The workers fought alone" in shown
    assert "AI-GENERATED  Open questions" in shown
    assert "FURTHER READING" in shown
    # The analysis comes before the passages it cites.
    assert shown.index("The workers fought alone") < shown.index("SOURCES")


@pytest.mark.parametrize("mode, text, error", [
    ("traditions", "the state", "needs a language model"),
    ("recommend", "", "Nothing is known about your interests yet"),
])
def test_a_request_that_cannot_be_served_says_why(gui, mode, text, error):
    window, _ = gui(seed=True)
    page = research_page(window)

    run(page, mode, text)

    assert error in page.message.text()
    assert page.run_button.isEnabled()


def test_an_empty_topic_is_refused_except_for_recommendations(gui):
    window, _ = gui(seed=True)
    page = research_page(window)

    run(page, "history", "   ")
    assert page.message.text() == "Type a question or topic first."


def test_recommendations_without_a_model_are_ranked_by_matches(gui):
    window, _ = gui(seed=True)

    shown = run(research_page(window), "recommend", "imperialism")

    assert "Readings on imperialism" in shown
    assert "Ranked by matching passages" in shown
    assert "Start reading ›" in shown


def test_history_and_analysis_label_their_ai_output(gui):
    history = ScriptedLLM(
        "search: Vienna 1848 | barricades workers Vienna",
        "overview: Vienna rose and fell [1].\nstage: March 1848 | The workers took the barricades [1].",
    )
    window, _ = gui(history, seed=True)
    shown = run(research_page(window), "history", "the Vienna insurrection of 1848")

    assert "Historical context: the Vienna insurrection of 1848" in shown
    assert "AI-GENERATED  How it developed, organised from the passages" in shown
    # The chronology is a table: the date in one cell, what happened in the next.
    assert "Chronology" in shown and "March 1848" in shown and "The workers took the barricades" in shown


def test_a_passage_link_opens_the_text_at_its_paragraph(gui):
    from PySide6.QtCore import QUrl

    window, _ = gui(seed=True)
    page = research_page(window)
    run(page, "ask", "Why are wages so low?")
    source = page.result.sources[0]
    link = f"praxis:read/{source.citation.document_id}/{source.citation.locator.lstrip('¶')}"

    page.output.anchorClicked.emit(QUrl(link))

    library = window.page("Library")
    assert window.current_title == "Library"
    assert library.text.document.id == source.citation.document_id
    assert library.opened_at == int(source.citation.locator.lstrip("¶"))


def test_a_citation_in_ai_text_scrolls_to_its_passage(gui):
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import QApplication

    llm = ScriptedLLM("minimum wage", "Wages are the cost of keeping the worker alive [6].")
    window, _ = gui(llm, seed=True)
    page = research_page(window)
    window.resize(900, 400)
    window.show()  # laid out, so the pane can scroll
    run(page, "ask", "Why are wages so low?")
    QApplication.processEvents()
    assert 'href="#src-6"' in page.output.toHtml()  # the [6] is a link
    scroll = page.output.verticalScrollBar()
    scroll.setValue(0)

    page.output.anchorClicked.emit(QUrl("#src-6"))

    assert scroll.value() > 0
