"""The annotate and annotations commands, and annotations in `library read` (F06)."""

import re

import pytest
from conftest import ScriptedLLM

from praxis import app as app_module
from praxis.cli import commands
from praxis.config import Settings


@pytest.fixture
def manifesto_id(run):
    assert run("library", "seed").exit_code == 0
    listing = run("library", "search", "Manifesto").output
    return re.search(r"^([0-9a-f]{8})  .*Manifesto", listing, re.MULTILINE).group(1)


def use_llm(monkeypatch, cli_database, *replies):
    llm = ScriptedLLM(*replies)
    monkeypatch.setattr(
        commands, "application_factory",
        lambda: app_module.build_application(Settings(openai_api_key=None), cli_database, llm),
    )
    return llm


def test_annotate_shows_the_text_then_a_marked_annotation(manifesto_id, run, monkeypatch, cli_database):
    use_llm(
        monkeypatch, cli_database,
        "The passage states that history is a history of class struggles.\n"
        "uncertain: whether this covers societies before written records",
    )
    result = run("annotate", manifesto_id, "5", "--type", "terminology")

    assert result.exit_code == 0, result.output
    output = result.output
    assert ", ¶5" in output
    assert "┃ AI annotation: terminology" in output
    assert "┃ The passage states that history" in output
    assert "Could not be verified:" in output
    assert "before written records" in output
    assert "(15 model tokens)" in output
    # The author's text comes first, the commentary after it.
    assert output.index(", ¶5") < output.index("AI annotation")


def test_context_annotation_lists_sources_with_links(manifesto_id, run, monkeypatch, cli_database):
    use_llm(monkeypatch, cli_database, "Engels makes the same point [1].")
    result = run("annotate", manifesto_id, "20", "-t", "historical-context")
    assert result.exit_code == 0, result.output
    assert "┃ [1] " in result.output
    assert "→ praxis library read " in result.output


def test_annotation_is_marked_in_library_read_and_shown_on_request(
    manifesto_id, run, monkeypatch, cli_database
):
    use_llm(monkeypatch, cli_database, "A note on the argument.")
    assert run("annotate", manifesto_id, "3").exit_code == 0

    plain = run("library", "read", manifesto_id, "--start", "2", "--count", "3").output
    assert "✎ 1 AI annotation (argument) — show with --annotations" in plain
    assert "A note on the argument." not in plain
    # The marker sits under ¶3, before ¶4.
    assert plain.index("[¶3]") < plain.index("✎") < plain.index("[¶4]")

    expanded = run("library", "read", manifesto_id, "--start", "3", "--count", "1", "-a").output
    assert "┃ A note on the argument." in expanded
    assert "✎" not in expanded


def test_annotations_list_and_remove(manifesto_id, run, monkeypatch, cli_database):
    use_llm(monkeypatch, cli_database, "Second paragraph note.", "First paragraph note.")
    run("annotate", manifesto_id, "12")
    run("annotate", manifesto_id, "4", "-t", "framing")

    listing = run("annotations", "list", manifesto_id).output
    assert listing.index("[¶4]") < listing.index("[¶12]")
    annotation_id = re.search(r"framing  \[([0-9a-f]{8})\]", listing).group(1)

    removed = run("annotations", "remove", annotation_id)
    assert removed.exit_code == 0, removed.output
    assert "First paragraph note." not in run("annotations", "list", manifesto_id).output


def test_without_a_key_annotate_fails_cleanly(manifesto_id, run):
    result = run("annotate", manifesto_id, "3")
    assert result.exit_code == 1
    assert "No language model is configured" in result.output


def test_unknown_type_and_paragraph_fail_cleanly(manifesto_id, run):
    bad_type = run("annotate", manifesto_id, "3", "--type", "summary")
    assert bad_type.exit_code == 1
    assert "fact-check" in bad_type.output
    bad_paragraph = run("annotate", manifesto_id, "100000")
    assert bad_paragraph.exit_code == 1
    assert "there is no ¶100000" in bad_paragraph.output


def test_list_without_annotations_explains_how_to_add_one(manifesto_id, run):
    assert "praxis annotate" in run("annotations", "list", manifesto_id).output


def test_list_items_in_an_annotation_stay_on_their_own_lines(manifesto_id, run, monkeypatch, cli_database):
    use_llm(
        monkeypatch, cli_database,
        "How the passages bear on the claims:\n- The date is supported.\n- The wording is not.",
    )
    output = run("annotate", manifesto_id, "3", "-t", "fact-check").output
    assert "┃ How the passages bear on the claims:\n" in output
    assert "┃ - The date is supported.\n" in output
    assert "┃ - The wording is not.\n" in output
