"""The recommend command (F07)."""

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


def test_without_a_model_texts_are_listed_by_matches(run):
    assert run("library", "seed").exit_code == 0
    result = run("recommend", "imperialism")

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Readings on imperialism  (ranked by matching passages)" in out
    assert "1. A Letter to American Workingmen (1918) — V. I. Lenin" in out
    assert re.search(r"→ praxis library read [0-9a-f]{8} --start \d+", out)
    assert "Keep one in your workspace:  praxis workspace save-text" in out
    assert "Note: Little is known about your reading" in out
    assert "No language model is configured" in out


def test_model_reasons_difficulty_and_external_works_are_shown(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    use_llm(
        monkeypatch, cli_database,
        "recommend: [1] | introductory | Lenin on the imperialist war, in a short letter.\n"
        "external: Imperialism, the Highest Stage of Capitalism | V. I. Lenin | The library lacks it.",
    )
    out = run("recommend", "imperialism").output

    assert "Readings on imperialism  (ranked by AI)" in out
    assert "[introductory]" in out
    assert "Why (AI-generated): Lenin on the imperialist war" in out
    assert "You have not opened it yet." in out
    assert "Not in the library (named by the AI, not checked)" in out
    assert "- Imperialism, the Highest Stage of Capitalism — V. I. Lenin: The library lacks it." in out
    assert "(15 model tokens)" in out


def test_reading_a_text_shows_progress_in_its_recommendation(run):
    assert run("library", "seed").exit_code == 0
    listing = run("library", "search", "Workingmen").output
    lenin = re.search(r"^([0-9a-f]{8})  ", listing, re.MULTILINE).group(1)
    assert run("library", "read", lenin, "--start", "1", "--count", "3").exit_code == 0

    out = run("recommend", "imperialism").output

    assert re.search(r"You have read \d+% of it\.", out)
    assert "Little is known" not in out


def test_without_a_topic_interests_are_used(run):
    assert run("library", "seed").exit_code == 0
    assert run("profile", "interest", "imperialism").exit_code == 0

    out = run("recommend").output

    assert "Readings on your interests (imperialism)" in out


def test_without_a_topic_or_interests_the_reader_is_told_what_to_do(run):
    result = run("recommend")

    assert result.exit_code == 1
    assert "Nothing is known about your interests yet" in result.output


def test_nothing_found_is_said(run):
    assert run("library", "seed").exit_code == 0
    out = run("recommend", "xylophone").output

    assert "No readings to recommend." in out
    assert "No text in the library discusses this topic." in out
