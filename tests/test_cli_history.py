"""The history command and news event --history (F09)."""

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


ACCOUNT = """\
overview: Germany's bourgeoisie rose and then sided with the crown [1].
origin: The March days in Berlin [1].
stage: March 1848 | Risings in Vienna and Berlin [1].
turning point: December 1848 | The Prussian Assembly was dissolved [2].
continuity: The army stayed with the crown [2].
interpretation: Engels blames the bourgeoisie's fear of the workers [1].
gap: Nothing on the countryside.
"""


def test_history_shows_steps_sources_and_the_organised_account(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    use_llm(monkeypatch, cli_database, "scope: focused |\nsearch: the risings | Vienna Berlin March", ACCOUNT)
    result = run("history", "the German revolution of 1848")

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Historical context: the German revolution of 1848" in out
    assert re.search(r"1\. ✓ the risings: Vienna Berlin March  \+\d+ sources?", out)
    assert "[1] " in out and "(history)" in out and "(cited)" in out
    assert "How it developed (AI-organised from the passages)" in out
    assert "Germany's bourgeoisie rose and then sided with the crown. [1]" in out
    assert "Chronology (as the passages state it)" in out
    assert "- March 1848: Risings in Vienna and Berlin. [1]" in out
    assert "- December 1848: turning point — The Prussian Assembly was dissolved. [2]" in out
    assert "Disputed interpretations (interpretation, not established fact)" in out
    assert "Gaps: what the passages do not cover" in out
    assert "Read further" in out
    assert re.search(r"Revolution and Counter-Revolution.*\(cited \d+ times?\)", out)


def test_a_too_broad_topic_suggests_narrower_ones(run, monkeypatch, cli_database):
    use_llm(monkeypatch, cli_database, "scope: too broad | the 1848 revolutions; the Paris Commune")
    out = run("history", "the history of capitalism").output

    assert "covers too much" in out
    assert 'praxis history "the 1848 revolutions"' in out
    assert 'praxis history "the history of capitalism" --broad' in out


def test_without_a_model_the_passages_are_shown(run):
    assert run("library", "seed").exit_code == 0
    out = run("history", "Vienna insurrection").output

    assert "Historical context: Vienna insurrection" in out
    assert "No language model is configured" in out
    assert "How it developed" not in out


def test_news_event_history_rejects_two_modes(run):
    result = run("news", "event", "abc", "--history", "--compare")

    assert result.exit_code != 0
    assert "Choose one of --research, --compare and --history." in result.output
