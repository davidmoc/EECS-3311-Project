"""--detail and --general: the reader's overrides for one request (F14)."""

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


def test_ask_with_less_detail_changes_this_answer_only(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    assert run("profile", "know", "wages", "advanced").exit_code == 0
    llm = use_llm(monkeypatch, cli_database, "minimum wage", "Wages are low [1].")

    out = run("ask", "Why are wages low?", "--detail", "brief").output

    assert "adapted to your reader profile" in out
    assert "two or three sentences" in llm.prompts[1].system
    assert "On this topic:\n- Says they are at advanced level in wages" in llm.prompts[1].system
    assert "explanation depth: standard" in run("profile", "show").output


def test_general_leaves_the_profile_out_of_one_request(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    assert run("profile", "know", "wages", "advanced").exit_code == 0
    llm = use_llm(monkeypatch, cli_database, "minimum wage", "Wages are low [1].")

    out = run("ask", "Why are wages low?", "--general").output

    assert "adapted to your reader profile" not in out
    assert "About the reader" not in llm.prompts[1].system
    assert "personalization: on" in run("profile", "show").output


def test_recommend_general_rests_on_the_topic_alone(run, monkeypatch, cli_database):
    assert run("library", "seed").exit_code == 0
    assert run("profile", "know", "the state", "advanced").exit_code == 0
    use_llm(monkeypatch, cli_database, "unreadable")

    out = run("recommend", "the state", "--general").output

    assert "Personalization is off, so these recommendations rest on the topic alone" in out


def test_an_unknown_detail_level_is_refused(run):
    result = run("ask", "Why?", "--detail", "enormous")

    assert result.exit_code == 2
    assert "enormous" in result.output
