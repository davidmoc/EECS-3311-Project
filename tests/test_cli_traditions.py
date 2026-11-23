"""The traditions and sessions traditions commands (F12)."""

import re

from conftest import ScriptedLLM

from praxis import app as app_module
from praxis.cli import commands
from praxis.config import Settings


def use_llm(monkeypatch, cli_database, *replies):
    llm = ScriptedLLM(*replies)
    monkeypatch.setattr(
        commands, "application_factory",
        lambda: app_module.build_application(Settings(openai_api_key=None), cli_database, llm),
    )
    return llm


TRADITIONS = (
    "perspective: Marxism | Friedrich Engels | state abolished withers | The platform's own.\n"
    "perspective: Anarchism | Peter Kropotkin | state abolish government | Rejects any state.\n"
    "perspective: Xylophonism | none | xylophone marimba | An invented tradition no text mentions."
)


def first_number(out, tradition):
    return re.search(rf"\[(\d+)\] .*\({tradition}, own words\)", out).group(1)


def test_traditions_shows_each_position_apart_from_the_marxist_assessment(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    use_llm(monkeypatch, cli_database, TRADITIONS, "unreadable")
    first = run("traditions", "the abolition of the state").output
    marxist, anarchist = first_number(first, "Marxism"), first_number(first, "Anarchism")

    reply = (
        f"position: Marxism | The state withers away after the proletariat takes power [{marxist}].\n"
        f"position: Anarchism | The state must be abolished at once [{anarchist}].\n"
        f"disagreement: Whether a workers' state is needed [{marxist}, {anarchist}].\n"
        f"assessment: Anarchism | Engels calls immediate abolition utopian [{marxist}, {anarchist}].\n"
        "gap: Nothing on the Paris Commune."
    )
    use_llm(monkeypatch, cli_database, TRADITIONS, reply)
    out = run("traditions", "the abolition of the state").output

    assert "Leftist traditions on: the abolition of the state" in out
    assert "Traditions (AI-chosen): Marxism (Friedrich Engels); Anarchism (Peter Kropotkin)" in out
    assert "Left out, no material in the library: Xylophonism" in out
    assert "Comparison (AI-generated from the passages)" in out
    assert f"- Position: The state must be abolished at once. [{anarchist}]" in out
    assert "- Marxist assessment (the platform's view, not its own): Engels calls" in out
    assert "Where they disagree" in out
    assert "Gaps: what the passages cannot show" in out
    assert "Read each tradition in its own words" in out
    assert "Anarchism: The Conquest of Bread — Peter Kropotkin" in out


def test_no_other_tradition_points_to_a_marxist_analysis(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    use_llm(
        monkeypatch, cli_database,
        "perspective: Marxism | Karl Marx | value commodity | Central.\n"
        "none: The traditions share this reading of value.",
    )
    out = run("traditions", "exchange value").output

    assert "No other leftist tradition differs materially on this topic (AI judgement)." in out
    assert "Why: The traditions share this reading of value." in out
    assert 'praxis analyze "exchange value"' in out


def test_traditions_needs_a_model(run):
    result = run("traditions", "the state")

    assert result.exit_code == 1
    assert "needs a language model" in result.output


def test_sessions_traditions_uses_the_research_question(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    use_llm(monkeypatch, cli_database, "evidence: state bourgeoisie", "verdict: sufficient", "## Findings\nIt rules [1].")
    research = run("research", "the state and the bourgeoisie").output
    short = re.search(r"Research session ([0-9a-f]{8})\.", research).group(1)

    llm = use_llm(monkeypatch, cli_database, TRADITIONS, "unreadable")
    out = run("sessions", "traditions", short).output

    assert f"Leftist traditions on: the state and the bourgeoisie  (research session {short})" in out
    assert "Topic: the state and the bourgeoisie" in llm.prompts[0].user
