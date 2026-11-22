"""The `research` command (F03)."""

import pytest
from conftest import ScriptedLLM

from praxis import app as app_module
from praxis.cli import commands
from praxis.config import Settings


@pytest.fixture
def seeded(run):
    assert run("library", "seed").exit_code == 0


def use_llm(monkeypatch, cli_database, *replies):
    llm = ScriptedLLM(*replies)
    monkeypatch.setattr(
        commands,
        "application_factory",
        lambda: app_module.build_application(Settings(openai_api_key=None), cli_database, llm),
    )
    return llm


def test_research_shows_steps_sources_analysis_and_questions(seeded, run, monkeypatch, cli_database):
    use_llm(
        monkeypatch, cli_database,
        "history: revolution 1848 Germany\ntheory: bourgeoisie proletariat",
        "verdict: sufficient",
        "## Findings\nThe German bourgeoisie feared the workers [1].\n\n"
        "## Open questions\n- How did the peasantry act?\n",
    )

    result = run("research", "Why did the 1848 revolution in Germany fail?")

    assert result.exit_code == 0, result.output
    out = result.output
    assert "1. ✓ Trace historical development: revolution 1848 Germany  +3 sources" in out
    assert "Stopped: the assessment found the research sufficiently developed." in out
    assert "[1] " in out and "(history)  (cited)" in out
    assert "Analysis (AI-generated)" in out
    assert "Findings\nThe German bourgeoisie feared the workers [1]." in out
    assert "Open questions (AI-generated)\n  - How did the peasantry act?" in out
    assert "Further reading" in out
    assert "model tokens" in out
    # AI text comes after the sources it is based on
    assert out.index("Sources") < out.index("Analysis (AI-generated)")


def test_research_budget_options_limit_the_steps(seeded, run, monkeypatch, cli_database):
    use_llm(
        monkeypatch, cli_database,
        "evidence: bourgeoisie\ntheory: surplus value\nhistory: enclosure",
        "## Findings\nX [1].",
    )

    result = run("research", "What is the bourgeoisie?", "--max-steps", "1")

    assert result.exit_code == 0, result.output
    assert "Stopped: the step limit was reached." in result.output
    assert "2. " not in result.output.split("Sources")[0]
    assert "Note: Research stopped early because the step limit was reached." in result.output


def test_research_without_a_model_still_lists_sources(seeded, run):
    result = run("research", "bourgeoisie and proletariat")

    assert result.exit_code == 0, result.output
    assert "Sources" in result.output
    assert "Analysis" not in result.output
    assert "No language model is configured" in result.output


def test_research_with_nothing_found_says_so(seeded, run, monkeypatch, cli_database):
    use_llm(monkeypatch, cli_database, "evidence: semiconductors microchips")

    result = run("research", "semiconductors microchips")

    assert result.exit_code == 0, result.output
    assert "No passage in the library bears on this research question" in result.output
    assert "Sources" not in result.output


def test_research_rejects_an_empty_question(run):
    result = run("research", "  ")

    assert result.exit_code == 1
    assert "Enter a research question first." in result.output


def test_research_shows_assessments_and_the_concrete_situation(seeded, run, monkeypatch, cli_database):
    use_llm(
        monkeypatch, cli_database,
        "history: revolution 1848 Germany",
        "contradiction: bourgeoisie | proletariat | the bourgeoisie feared the workers [1]\n"
        "conflict: The sources differ on who betrayed the revolution [1, 2]\n"
        "search: theory | state power\n"
        "verdict: more research needed",
        "verdict: sufficient",
        "## Findings\nThe bourgeoisie retreated [1].",
    )

    result = run("research", "Why did the 1848 revolution in Germany fail?")

    assert result.exit_code == 0, result.output
    out = result.output
    assert "✓ ◆ Assess the research so far: 1 contradiction, 1 conflict between sources; 1 search added" in out
    assert "Retrieve theory: state power" in out
    assert "Concrete situation (AI-assessed; each point cites the sources above)" in out
    assert "  - bourgeoisie vs proletariat: the bourgeoisie feared the workers [1]" in out
    assert "Where the sources disagree" in out and "betrayed the revolution [1, 2]" in out
    assert out.index("Sources") < out.index("Concrete situation") < out.index("Analysis (AI-generated)")
