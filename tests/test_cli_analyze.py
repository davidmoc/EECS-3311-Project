"""The analyze and sessions analyze commands (F11)."""

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


CONCEPTS = "concept: class struggle | class struggles freeman slave | The workers fought."


def analysis_reply(evidence, theory):
    return (
        f"condition: class | The workers fought in Vienna [{evidence}].\n"
        f"application: class struggle | The history of class struggles frames it [{theory}, {evidence}].\n"
        f"claim: tentative | The bourgeoisie feared the workers [{evidence}].\n"
        f"alternative: Military weakness explains more [{evidence}].\n"
        "limit: Nothing on the peasantry."
    )


def numbers_by_purpose(out):
    evidence = re.search(r"\[(\d+)\] .*\(evidence\)", out).group(1)
    theory = re.search(r"\[(\d+)\] .*\(theory\)", out).group(1)
    return evidence, theory


def test_analyze_shows_sources_then_the_marked_analysis(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    # Find the numbers the sources will get, with no model, to script the reply.
    plain = run("analyze", "Vienna insurrection").output
    assert "No language model is configured" in plain
    use_llm(monkeypatch, cli_database, "", CONCEPTS, "")
    first = run("analyze", "Vienna insurrection", "--framework", "class struggle").output
    evidence, theory = numbers_by_purpose(first)

    use_llm(monkeypatch, cli_database, "", CONCEPTS, analysis_reply(evidence, theory))
    out = run("analyze", "Vienna insurrection", "--framework", "class struggle").output

    assert "Marxist analysis: Vienna insurrection" in out
    assert "Framework requested: class struggle" in out
    assert "Concepts applied (AI-chosen): class struggle" in out
    assert "Analysis (AI-generated interpretation)" in out
    assert "What the evidence shows" in out and f"- class: The workers fought in Vienna. [{evidence}]" in out
    assert f"- class struggle: The history of class struggles frames it. [{theory}, {evidence}]" in out
    assert "- (tentative) The bourgeoisie feared the workers." in out
    assert "Other readings within Marxist analysis" in out
    assert "Limits: where the theory may not fit or the evidence is thin" in out
    assert "Theory to study further" in out
    assert "Note: No claim in this analysis is borne out by several evidence passages" in out


def test_sessions_analyze_names_the_session(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    use_llm(monkeypatch, cli_database, "evidence: Vienna insurrection", "verdict: sufficient", "## Findings\nIt failed [1].")
    research = run("research", "Why did the Vienna insurrection fail?").output
    short = re.search(r"Research session ([0-9a-f]{8})\.", research).group(1)

    use_llm(monkeypatch, cli_database, CONCEPTS, "")
    out = run("sessions", "analyze", short).output

    assert f"Marxist analysis: Why did the Vienna insurrection fail?  (on research session {short})" in out
    assert "The model's analysis could not be read" in out


def test_analyze_of_nothing_found_says_so(run):
    assert run("library", "seed").exit_code == 0
    out = run("analyze", "xylophone").output

    assert "No passage in the library bears on this issue" in out
