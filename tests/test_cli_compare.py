"""The compare command (F10)."""

import re

import pytest
from conftest import ScriptedLLM

from praxis import app as app_module
from praxis.cli import commands
from praxis.config import Settings


@pytest.fixture
def ids(run):
    assert run("library", "seed").exit_code == 0

    def find(title):
        listing = run("library", "search", title).output
        return re.search(rf"^([0-9a-f]{{8}})  .*{title}", listing, re.MULTILINE).group(1)

    return find("Manifesto"), find("Counter-Revolution")


def use_llm(monkeypatch, cli_database, *replies):
    llm = ScriptedLLM(*replies)
    monkeypatch.setattr(
        commands, "application_factory",
        lambda: app_module.build_application(Settings(openai_api_key=None), cli_database, llm),
    )
    return llm


REPLY = """\
comparability: partly comparable | the Manifesto is a programme, Lenin a polemic
similarity: both call the state an instrument of class rule [1, 3]
difference: terminology | "committee" against "organ of oppression" [1, 3]
disagreement: they date the change differently [2, 4]
observation: Lenin argues against reformist readers [3]
uncertain: whether Lenin quotes this edition
"""


def test_compare_shows_lettered_sources_then_the_marked_comparison(ids, run, monkeypatch, cli_database):
    manifesto, lenin = ids
    use_llm(monkeypatch, cli_database, REPLY)
    result = run("compare", f"{manifesto}:20-21", f"{lenin}:30,31", "--on", "the state")

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Comparing on: the state" in out
    assert "Source A: " in out and "Manifesto" in out
    assert "Source B: " in out and "Counter-Revolution" in out
    assert "[1] ¶20" in out and "[2] ¶21" in out and "[3] ¶30" in out and "[4] ¶31" in out
    assert f"→ praxis library read {manifesto} --start 20" in out
    assert "Comparability (AI-assessed): partly comparable — the Manifesto is a programme" in out
    assert "Shared ground (AI-generated)" in out
    assert "[1, 3] (sources A, B)" in out
    assert '- terminology: "committee" against' in out
    assert "Factual disagreements" in out
    assert "Observations on framing (AI interpretation, not established fact)" in out
    assert "[3] (source B)" in out
    assert "whether Lenin quotes this edition" in out
    # The passages come before any AI-generated comparison.
    assert out.index("[4] ¶31") < out.index("Comparability")


def test_compare_without_a_key_shows_only_the_passages(ids, run):
    manifesto, lenin = ids
    result = run("compare", manifesto, lenin, "--on", "the state")
    assert result.exit_code == 0, result.output
    assert "Source A: " in result.output and "Source B: " in result.output
    assert "No language model is configured" in result.output
    assert "AI-generated" not in result.output


def test_whole_texts_need_a_subject(ids, run):
    manifesto, lenin = ids
    result = run("compare", manifesto, lenin)
    assert result.exit_code == 1
    assert "what to compare the sources on" in result.output


@pytest.mark.parametrize("spec", [":abc", ":5-x", ":9-3"])
def test_bad_paragraph_specs_are_reported(ids, run, spec):
    manifesto, lenin = ids
    result = run("compare", manifesto + spec, lenin + ":1")
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_a_missing_paragraph_leaves_the_source_out(ids, run):
    manifesto, lenin = ids
    result = run("compare", f"{manifesto}:99999", f"{lenin}:30")
    assert result.exit_code == 0, result.output
    assert "there is no ¶99999" in result.output
    assert "Fewer than two of the chosen sources" in result.output
