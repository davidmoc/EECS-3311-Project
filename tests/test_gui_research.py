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
    assert "Sources" in shown and "open in the library" in shown
    assert "No language model is configured" in shown


def test_a_question_with_less_detail_is_explained_for_this_request(gui):
    llm = ScriptedLLM("minimum wage", "Wages are the cost of keeping the worker alive [1].")
    window, application = gui(llm, seed=True)
    page = research_page(window)
    page.choose("ask")
    page.detail_box.setCurrentIndex(page.detail_box.findData(ExplanationDepth.BRIEF))

    shown = run(page, "ask", "Why are wages so low?")

    assert "Explanation (AI-generated)" in shown
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

    assert "Research steps" in shown and "✓" in shown
    assert "Analysis (AI-generated)" in shown
    assert "The workers fought alone" in shown
    assert "Open questions (AI-generated)" in shown
    assert "Further reading" in shown


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
    assert "ranked by matching passages" in shown
    assert "start reading" in shown


def test_history_and_analysis_label_their_ai_output(gui):
    history = ScriptedLLM(
        "search: Vienna 1848 | barricades workers Vienna",
        "overview: Vienna rose and fell [1].\nstage: March 1848 | The workers took the barricades [1].",
    )
    window, _ = gui(history, seed=True)
    shown = run(research_page(window), "history", "the Vienna insurrection of 1848")

    assert "Historical context: the Vienna insurrection of 1848" in shown
    assert "How it developed, organised from the passages (AI-generated)" in shown
    assert "March 1848: The workers took the barricades" in shown


def test_a_passage_link_opens_the_text_at_its_paragraph(gui):
    from PySide6.QtCore import QUrl

    window, _ = gui(seed=True)
    page = research_page(window)
    run(page, "ask", "Why are wages so low?")
    source = page.result.sources[0]
    link = f"praxis:read/{source.citation.document_id}/{source.citation.locator.lstrip('¶')}"

    page._link_clicked(QUrl(link))

    library = window.page("Library")
    assert window.current_title == "Library"
    assert library.page.document.id == source.citation.document_id
    assert library.page.start == int(source.citation.locator.lstrip("¶"))
