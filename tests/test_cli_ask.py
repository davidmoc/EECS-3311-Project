import pytest

from praxis import app as app_module
from praxis.cli import commands
from praxis.config import Settings
from praxis.llm import LLMClient, LLMResponse


class ScriptedLLM(LLMClient):
    def __init__(self, *replies):
        self.replies = list(replies)

    def generate(self, prompt):
        return LLMResponse(self.replies.pop(0), "fake", 100, 20)


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


def test_ask_shows_passages_then_labelled_explanation(seeded, run, monkeypatch, cli_database):
    use_llm(
        monkeypatch, cli_database,
        "minimum wage, means of subsistence",
        "The Manifesto says the price of labour is its cost of production [1].",
    )

    result = run("ask", "Why are wages so low?")

    assert result.exit_code == 0, result.output
    output = result.output
    assert output.index("Sources") < output.index("Explanation (AI-generated)")
    assert "[1] " in output and "(cited)" in output
    assert "→ praxis library read " in output
    assert "cost of production [1]" in output
    assert "(240 model tokens)" in output


def test_ask_without_a_key_still_shows_passages(seeded, run):
    result = run("ask", "What is the bourgeoisie?")

    assert result.exit_code == 0
    assert "Sources" in result.output
    assert "Explanation" not in result.output
    assert "OPENAI_API_KEY" in result.output


def test_ask_about_something_the_library_lacks(seeded, run, monkeypatch, cli_database):
    use_llm(monkeypatch, cli_database, "cryptocurrency, blockchain")

    result = run("ask", "Is bitcoin a blockchain?")

    assert result.exit_code == 0
    assert "Sources" not in result.output
    assert "No passage in the library addresses this question" in result.output


def test_ask_rejects_an_empty_question(run):
    result = run("ask", "  ")

    assert result.exit_code == 1
    assert "Ask a question first" in result.output


def test_ask_save_puts_the_answer_in_the_workspace(seeded, run, monkeypatch, cli_database):
    use_llm(monkeypatch, cli_database, "bourgeoisie", "The bourgeoisie rules [1].")

    result = run("ask", "Who rules?", "--save", "-t", "state")

    assert result.exit_code == 0, result.output
    assert "Saved to your workspace" in result.output
    listing = run("workspace", "list", "--kind", "research").output
    assert "[research] Q: Who rules?" in listing
    assert "tags: state" in listing


def test_ask_save_with_no_sources_saves_nothing(seeded, run, monkeypatch, cli_database):
    use_llm(monkeypatch, cli_database, "blockchain")

    result = run("ask", "Is bitcoin a blockchain?", "--save")

    assert "Nothing was saved" in result.output
    assert "empty" in run("workspace", "list").output
