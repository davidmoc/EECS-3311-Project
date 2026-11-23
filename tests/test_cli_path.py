"""The path commands (F08)."""

import re

from conftest import ScriptedLLM

from praxis import app as app_module
from praxis.cli import commands
from praxis.config import Settings

REPLY = """\
prerequisite: Class struggle | concept | essential
search: class struggles, freeman and slave
why: The target reads history as class conflict.
orientation: History moves through conflicts between classes.

prerequisite: Physiocrats | theory | helpful
search: Physiocrats
why: The method answers them.
orientation: French economists who held land the only source of value.
"""


def use_llm(monkeypatch, cli_database, *replies):
    llm = ScriptedLLM(*replies)
    monkeypatch.setattr(
        commands, "application_factory",
        lambda: app_module.build_application(Settings(openai_api_key=None), cli_database, llm),
    )
    return llm


def text_id(run, title):
    listing = run("library", "search", title).output
    return re.search(rf"^([0-9a-f]{{8}})  .*{title}", listing, re.MULTILINE).group(1)


def test_build_shows_ordered_steps_with_readings_and_gaps(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    use_llm(monkeypatch, cli_database, REPLY)
    result = run("path", "build", "historical materialism")

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Learning path for historical materialism  (prerequisites identified by AI)" in out
    assert "1. Class struggle  — concept, suggested" in out
    assert "Why (AI-generated): The target reads history as class conflict." in out
    assert re.search(r"Read: .*“The Communist Manifesto”, ¶\d+", out)
    assert re.search(r"→ praxis library read [0-9a-f]{8} --start \d+", out)
    assert "2. Physiocrats  — theory, suggested" in out
    # No bundled text mentions the Physiocrats.
    assert "Orientation (AI-generated; nothing in the library on this): French economists" in out
    assert 'praxis profile know "<name>" introductory' in out
    assert "Note: Little is known about what you already understand" in out


def test_known_prerequisites_are_left_out(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    assert run("profile", "know", "class struggle", "intermediate").exit_code == 0
    llm = use_llm(monkeypatch, cli_database, REPLY)
    out = run("path", "build", "historical materialism").output

    assert "checked against your reader profile" in out
    assert "Left out, as you said you know: Class struggle" in out
    assert "1. Physiocrats  — theory, suggested" in out
    assert "already knows: class struggle" in llm.prompts[0].user


def test_no_path_needed_points_to_the_target_text(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    assert run("profile", "know", "class struggle", "introductory").exit_code == 0
    manifesto = text_id(run, "Manifesto")
    use_llm(monkeypatch, cli_database, "prerequisite: Class struggle | concept | essential")
    out = run("path", "build", "--text", manifesto).output

    assert "Learning path for the text “The Communist Manifesto” (1848)" in out
    assert "no path is needed" in out
    assert f"→ praxis library read {manifesto}" in out


def test_build_needs_a_target(run):
    result = run("path", "build")

    assert result.exit_code == 1
    assert "Name a topic, or a text with --text." in result.output


def test_build_without_a_model_is_an_error(run):
    result = run("path", "build", "surplus value")

    assert result.exit_code == 1
    assert "No language model is configured" in result.output
