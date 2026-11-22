"""The `sessions` commands and the continue hint of `research` (F03, UC15)."""

import re

import pytest
from test_cli_research import use_llm

QUESTION = "Why did the 1848 revolution in Germany fail?"
PLAN = "history: revolution 1848 Germany\ntheory: bourgeoisie proletariat"
SYNTHESIS = "## Findings\nThe German bourgeoisie feared the workers [1].\n"


@pytest.fixture
def seeded(run):
    assert run("library", "seed").exit_code == 0


def session_id(output):
    return re.search(r"Research session ([0-9a-f]{8})\.", output).group(1)


def test_research_names_its_session_and_how_to_continue(seeded, run, monkeypatch, cli_database):
    use_llm(monkeypatch, cli_database, PLAN, "verdict: sufficient", SYNTHESIS)

    result = run("research", QUESTION)

    assert result.exit_code == 0, result.output
    short = session_id(result.output)
    assert f'praxis sessions continue {short} --focus "..."' in result.output
    assert "Run the remaining steps" not in result.output  # nothing was left unrun


def test_an_incomplete_session_is_listed_shown_and_continued(seeded, run, monkeypatch, cli_database):
    use_llm(monkeypatch, cli_database, PLAN, SYNTHESIS)
    first = run("research", QUESTION, "--max-tool-calls", "1")
    short = session_id(first.output)
    assert f"Run the remaining steps:  praxis sessions continue {short}" in first.output

    listed = run("sessions", "list")
    assert f"{short}  " in listed.output and QUESTION in listed.output
    assert "incomplete, 3 sources" in listed.output

    shown = run("sessions", "show", short)
    assert shown.exit_code == 0, shown.output
    assert shown.output.startswith("This research is incomplete.")
    assert "Analysis (AI-generated)" in shown.output

    use_llm(monkeypatch, cli_database, "verdict: sufficient", SYNTHESIS)
    continued = run("sessions", "continue", short)
    assert continued.exit_code == 0, continued.output
    assert "  Round 1\n" in continued.output and "  Round 2\n" in continued.output
    assert "Retrieve theory: bourgeoisie proletariat" in continued.output.split("Round 2")[1]

    listed = run("sessions", "list")
    assert "complete" in listed.output and "incomplete" not in listed.output
    assert "2 rounds" in listed.output


def test_continuing_with_a_focus_labels_the_round(seeded, run, monkeypatch, cli_database):
    use_llm(monkeypatch, cli_database, PLAN, "verdict: sufficient", SYNTHESIS)
    short = session_id(run("research", QUESTION).output)

    use_llm(monkeypatch, cli_database, "theory: wage labour", "verdict: sufficient", SYNTHESIS)
    result = run("sessions", "continue", short, "--focus", "the peasantry")

    assert result.exit_code == 0, result.output
    assert "  Round 2: the peasantry" in result.output


def test_continuing_finished_research_needs_a_focus(seeded, run, monkeypatch, cli_database):
    use_llm(monkeypatch, cli_database, PLAN, "verdict: sufficient", SYNTHESIS)
    short = session_id(run("research", QUESTION).output)

    result = run("sessions", "continue", short)

    assert result.exit_code == 1
    assert "Give a direction to continue in." in result.output


def test_unknown_session_and_empty_list(run):
    assert "No research yet." in run("sessions", "list").output
    result = run("sessions", "show", "deadbeef")
    assert result.exit_code == 1
    assert "No research session with id starting 'deadbeef'." in result.output


def test_saved_research_is_reopened_from_the_workspace(seeded, run, monkeypatch, cli_database):
    use_llm(monkeypatch, cli_database, PLAN, "verdict: sufficient", SYNTHESIS)
    first = run("research", QUESTION, "--save", "--tag", "1848")
    short = session_id(first.output)
    item = re.search(r"Saved to your workspace \[([0-9a-f]{8})\]", first.output).group(1)

    opened = run("workspace", "open", item)

    assert opened.exit_code == 0, opened.output
    assert f"[research] Research: {QUESTION}" in opened.output
    assert "Analysis (AI-generated):" in opened.output
    assert f"→ praxis sessions continue {short}" in opened.output

    # Continuing and saving again updates the same workspace item.
    use_llm(monkeypatch, cli_database, "theory: wage labour", "verdict: sufficient", SYNTHESIS)
    again = run("sessions", "continue", short, "--focus", "wages", "--save")
    assert f"Saved to your workspace [{item}]" in again.output
    assert run("workspace", "list").output.count("Research: ") == 1
