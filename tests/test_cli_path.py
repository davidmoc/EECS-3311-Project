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
    assert re.search(r"Learning path [0-9a-f]{8}, 0 of 2 steps dealt with\.", out)
    assert "Next: step 1, Class struggle." in out
    assert re.search(r"Record progress:  praxis path mark [0-9a-f]{8} <step> done\|known\|skip", out)
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


def built_path(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    use_llm(monkeypatch, cli_database, REPLY)
    out = run("path", "build", "historical materialism").output
    return re.search(r"Learning path ([0-9a-f]{8}),", out).group(1)


def test_paths_are_listed_with_progress(run, monkeypatch, cli_database):
    path = built_path(run, monkeypatch, cli_database)

    out = run("path", "list").output

    assert re.search(rf"^{path}  .*  0/2 steps  historical materialism$", out, re.MULTILINE)


def test_marking_a_step_done_updates_the_reader_model(run, monkeypatch, cli_database):
    path = built_path(run, monkeypatch, cli_database)

    result = run("path", "mark", path, "1", "done")

    assert result.exit_code == 0, result.output
    assert "Step 1 (Class struggle): done." in result.output
    assert "Your reader model now counts you as knowing Class struggle" in result.output
    assert "1 of 2 steps dealt with." in result.output
    assert "Next: step 2, Physiocrats." in result.output
    profile = run("profile", "show").output
    assert re.search(r"class struggle: introductory", profile)


def test_skipping_does_not_touch_the_reader_model(run, monkeypatch, cli_database):
    path = built_path(run, monkeypatch, cli_database)

    out = run("path", "mark", path, "2", "skip").output

    assert "Step 2 (Physiocrats): skipped." in out
    assert "reader model" not in out
    assert "physiocrats" not in run("profile", "show").output


def test_show_marks_settled_steps_and_completing_points_onward(run, monkeypatch, cli_database):
    path = built_path(run, monkeypatch, cli_database)
    run("path", "mark", path, "1", "known")
    last = run("path", "mark", path, "2", "skip").output

    assert 'Path complete. On to the topic: praxis recommend "historical materialism"' in last
    out = run("path", "show", path).output
    assert "1. Class struggle  — concept, suggested  ✓ already known" in out
    assert "2. Physiocrats  — theory, suggested  – skipped" in out
    assert "2 of 2 steps dealt with." in out
    assert "model tokens" not in out


def test_mark_refuses_an_unknown_status_or_step(run, monkeypatch, cli_database):
    path = built_path(run, monkeypatch, cli_database)

    bad_status = run("path", "mark", path, "1", "finished")
    bad_step = run("path", "mark", path, "9", "done")

    assert bad_status.exit_code == 1 and "Use done, known, skip or todo." in bad_status.output
    assert bad_step.exit_code == 1 and "there is no step 9" in bad_step.output


def test_an_empty_path_list_says_how_to_start(run):
    assert "No learning paths yet." in run("path", "list").output
