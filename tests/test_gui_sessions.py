"""The past research page: reopen and continue stored research (F03, UC15)."""

from conftest import ScriptedLLM

RESEARCH = (
    "evidence: barricades Vienna workers", "verdict: sufficient",
    "## Findings\nThe workers fought alone [1].\n\n## Open questions\n- Why did the peasants stay home?",
)


def researched(gui, *more_replies):
    window, application = gui(ScriptedLLM(*RESEARCH, *more_replies), seed=True)
    research = window.show_page("Research")
    research.choose("research")
    research.input.setText("Why did the Vienna insurrection fail?")
    research.run_button.click()
    return window, application, research.result.session.id


def test_stored_research_is_listed_and_reopened(gui):
    window, _, session_id = researched(gui)
    page = window.show_page("Past research")

    assert page.session_list.count() == 1
    assert page.session_list.item(0).text().startswith("Why did the Vienna insurrection fail?")
    assert not page.continue_button.isEnabled()

    page._open_item(page.session_list.item(0))

    assert page.selected == session_id
    assert "The workers fought alone" in page.output.toPlainText()
    assert page.continue_button.isEnabled() and page.analyze_button.isEnabled()


def test_research_continues_with_a_new_focus(gui):
    # The follow-up plan, the assessment, then the rewritten analysis.
    window, application, session_id = researched(
        gui, "evidence: peasants Austria", "verdict: sufficient",
        "## Findings\nThe peasants stayed home [2].",
    )
    page = window.show_page("Past research")
    page.open_session(session_id)
    page.focus.setText("the peasants")

    page.continue_button.click()

    assert "The peasants stayed home" in page.output.toPlainText()
    assert "2 rounds" in page.session_list.item(0).text()
    assert application.agent.get_research(session_id).session.rounds == 2


def test_comparing_a_sessions_texts_shows_the_passages_even_if_the_model_fails_to_compare(gui):
    window, _, session_id = researched(gui, "Not in the comparison format.")
    page = window.show_page("Past research")
    page.open_session(session_id)

    page.compare_button.click()

    shown = page.output.toPlainText()
    assert shown.startswith("Comparing on: Why did the Vienna insurrection fail?")
    assert "Source A:" in shown and "Source B:" in shown
    assert "could not be read" in shown
    assert page.compare_button.isEnabled()


def test_with_no_research_the_page_says_where_to_start(gui):
    window, _ = gui()
    page = window.show_page("Past research")

    assert "No research yet" in page.output.toPlainText()
    assert not page.analyze_button.isEnabled()
