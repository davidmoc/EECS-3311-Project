"""PrerequisiteService and learning paths (F08, UC08, SD05)."""

from datetime import datetime

import pytest
from conftest import ScriptedLLM

from praxis.agent.prompts import MAX_PREREQUISITES, PromptBuilder
from praxis.llm import LLMError
from praxis.persistence import SQLDocumentRepository
from praxis.reader_model import AssessmentSource, KnowledgeLevel, ReaderProfile
from praxis.reading.prerequisites import (
    PERSONALIZATION_OFF_WARNING,
    SPARSE_PROFILE_WARNING,
    PrerequisiteError,
    PrerequisiteService,
    parse_prerequisites,
)
from praxis.tools import PassageSearchTool, ToolManager

REPLY = """\
prerequisite: Class struggle | concept | essential
search: class struggles, freeman and slave
why: The target reads history as class conflict.
orientation: Marx and Engels hold that history moves through conflicts between classes.

prerequisite: The 1848 revolutions | event | helpful
search: 1848 revolution bourgeoisie monarchy
why: The text responds to their defeat.
orientation: A wave of risings across Europe in 1848, mostly defeated by 1849.

prerequisite: Hegelian dialectic | theory | essential
search: negation of the negation
why: The method borrows from it.
orientation: Hegel's account of development through contradiction; how far Marx kept it is disputed.
"""


def service(database, llm):
    tools = ToolManager()
    tools.register_tool(PassageSearchTool(SQLDocumentRepository(database)))
    return PrerequisiteService(tools, llm)


def reader_who_knows(topic, source=AssessmentSource.USER_STATED, level=KnowledgeLevel.INTRODUCTORY):
    profile = ReaderProfile()
    profile.knowledge.update_level(topic, level, source)
    return profile


# --- parsing -------------------------------------------------------------------


def test_parse_reads_blocks_in_order():
    prerequisites = parse_prerequisites(REPLY)

    assert [p.name for p in prerequisites] == ["Class struggle", "The 1848 revolutions", "Hegelian dialectic"]
    first = prerequisites[0]
    assert (first.kind, first.essential, first.search) == ("concept", True, "class struggles, freeman and slave")
    assert first.why == "The target reads history as class conflict."
    assert first.orientation.startswith("Marx and Engels hold")
    assert prerequisites[1].kind == "event" and not prerequisites[1].essential


def test_parse_tolerates_missing_fields_and_unknown_kinds():
    prerequisites = parse_prerequisites("1. prerequisite: Value\nprerequisite: Rent | idea")

    assert [(p.name, p.kind, p.essential) for p in prerequisites] == [
        ("Value", "concept", True), ("Rent", "concept", True),
    ]


def test_parse_keeps_each_name_once_and_caps_the_list():
    reply = "\n".join(f"prerequisite: Topic {n % 7}" for n in range(20))
    prerequisites = parse_prerequisites(reply + "\nprerequisite: topic 1")

    assert len(prerequisites) == MAX_PREREQUISITES
    assert len({p.name.lower() for p in prerequisites}) == MAX_PREREQUISITES


def test_parse_of_another_form_finds_nothing():
    assert parse_prerequisites("You should first learn about class struggle.") == []


def test_prompt_lists_known_topics_only_when_given():
    builder = PromptBuilder()

    assert "already knows" not in builder.build_prerequisite_prompt("surplus value", []).user
    prompt = builder.build_prerequisite_prompt("surplus value", ["class struggle", "value"])
    assert prompt.user.endswith("Topics the reader already knows: class struggle; value")
    assert "essential|helpful" in prompt.system


# --- building a path -------------------------------------------------------------


def test_path_orders_steps_and_finds_readings(library_database):
    path = service(library_database, ScriptedLLM(REPLY)).build_learning_path("the Eighteenth Brumaire")

    assert [s.name for s in path.steps] == ["Class struggle", "The 1848 revolutions", "Hegelian dialectic"]
    assert path.steps[0].readings[0].locator == "¶1"
    assert "class struggles" in path.steps[0].readings[0].quoted_text
    assert path.steps[1].readings[0].document_title == "Revolution and Counter-Revolution in Germany"
    assert path.tokens_used == 15


def test_a_prerequisite_the_library_lacks_is_a_gap_with_its_orientation(library_database):
    path = service(library_database, ScriptedLLM(REPLY)).build_learning_path("the Eighteenth Brumaire")

    hegel = path.steps[2]
    assert hegel.is_gap
    assert hegel.prerequisite.orientation.startswith("Hegel's account")
    assert path.gaps == [hegel]
    assert any("nothing on Hegelian dialectic" in w for w in path.warnings)


def test_readings_come_from_different_texts_first(library_database):
    reply = "prerequisite: The bourgeoisie | concept | essential\nsearch: bourgeoisie"
    path = service(library_database, ScriptedLLM(reply)).build_learning_path("1848")

    titles = [c.document_title for c in path.steps[0].readings]
    assert len(set(titles)) == 2


def test_a_target_text_is_not_its_own_prerequisite_reading(library_database):
    manifesto = next(d for d in SQLDocumentRepository(library_database).list_all() if "Manifesto" in d.title)
    llm = ScriptedLLM("prerequisite: Class struggle | concept | essential\nsearch: class struggles")
    path = service(library_database, llm).build_learning_path("", document=manifesto)

    assert path.target.startswith("the text “The Communist Manifesto”")
    assert path.target_document_id == manifesto.id
    assert all(c.document_title != manifesto.title for c in path.steps[0].readings)
    assert "Target: the text “The Communist Manifesto”" in llm.prompts[0].user


def test_prerequisites_the_reader_said_they_know_are_left_out(library_database):
    profile = reader_who_knows("class struggle")
    llm = ScriptedLLM(REPLY)
    path = service(library_database, llm).build_learning_path("the Brumaire", profile)

    assert [s.name for s in path.steps] == ["The 1848 revolutions", "Hegelian dialectic"]
    assert path.already_known == ("Class struggle",)
    assert path.personalized
    assert "already knows: class struggle" in llm.prompts[0].user


def test_knowledge_only_inferred_from_reading_makes_a_suggestion(library_database):
    profile = reader_who_knows("class struggle", AssessmentSource.INFERRED)
    path = service(library_database, ScriptedLLM(REPLY)).build_learning_path("the Brumaire", profile)

    step = path.steps[0]
    assert step.name == "Class struggle"
    assert not step.required
    assert "may already know this" in step.note
    assert path.already_known == ()


def test_essential_steps_are_required_once_the_reader_is_known(library_database):
    profile = reader_who_knows("wages")
    path = service(library_database, ScriptedLLM(REPLY)).build_learning_path("the Brumaire", profile)

    assert [s.required for s in path.steps] == [True, False, True]


def test_with_little_known_every_step_is_a_suggestion(library_database):
    path = service(library_database, ScriptedLLM(REPLY)).build_learning_path("the Brumaire", ReaderProfile())

    assert not any(s.required for s in path.steps)
    assert SPARSE_PROFILE_WARNING in path.warnings
    assert not path.personalized


def test_personalization_off_does_not_filter(library_database):
    profile = reader_who_knows("class struggle")
    profile.personalization_enabled = False
    llm = ScriptedLLM(REPLY)
    path = service(library_database, llm).build_learning_path("the Brumaire", profile)

    assert len(path.steps) == 3
    assert PERSONALIZATION_OFF_WARNING in path.warnings
    assert "already knows" not in llm.prompts[0].user


def test_no_path_is_required_when_everything_is_known(library_database):
    profile = reader_who_knows("class struggle")
    llm = ScriptedLLM("prerequisite: Class struggle | concept | essential")
    path = service(library_database, llm).build_learning_path("the Manifesto", profile)

    assert path.steps == []
    assert path.no_path_required


def test_without_a_model_no_path_is_built(library_database):
    with pytest.raises(PrerequisiteError, match="No language model"):
        service(library_database, None).build_learning_path("the Brumaire")


def test_model_failure_and_unreadable_replies_are_errors(library_database):
    with pytest.raises(PrerequisiteError, match="timeout"):
        service(library_database, ScriptedLLM(LLMError("timeout"))).build_learning_path("x")
    with pytest.raises(PrerequisiteError, match="could not be read"):
        service(library_database, ScriptedLLM("Learn Hegel first.")).build_learning_path("x")


def test_an_empty_target_is_refused(library_database):
    with pytest.raises(PrerequisiteError):
        service(library_database, ScriptedLLM(REPLY)).build_learning_path("  ")


def test_interests_and_reading_alone_do_not_make_steps_required(library_database):
    # A live run marked every step "needed" for a reader whose profile held
    # only interests and reading progress, no knowledge at all.
    profile = ReaderProfile()
    profile.interests.add("1848")
    manifesto = next(d for d in SQLDocumentRepository(library_database).list_all() if "Manifesto" in d.title)
    profile.history.record(manifesto.id, manifesto.title, 1, 3, datetime(2026, 11, 1))

    path = service(library_database, ScriptedLLM(REPLY)).build_learning_path("the Brumaire", profile)

    assert not any(s.required for s in path.steps)
    assert SPARSE_PROFILE_WARNING in path.warnings


def test_a_target_text_is_named_without_its_catalogue_topics(library_database):
    repository = SQLDocumentRepository(library_database)
    manifesto = next(d for d in repository.list_all() if "Manifesto" in d.title)
    manifesto.topics = ("class struggle", "communism")
    llm = ScriptedLLM("prerequisite: Feudalism | concept | essential")

    service(library_database, llm).build_learning_path("", document=manifesto)

    assert "communism" not in llm.prompts[0].user


def test_a_passage_is_offered_by_one_step_only(library_database):
    # A live run offered the same paragraph for two neighbouring events.
    reply = (
        "prerequisite: The 1848 revolutions | event | essential\nsearch: 1848 revolution Paris\n"
        "prerequisite: The German revolution | event | essential\nsearch: 1848 revolution Germany\n"
    )
    path = service(library_database, ScriptedLLM(reply)).build_learning_path("the Brumaire")

    first, second = (set(c.locator for c in s.readings if "Revolution" in c.document_title) for s in path.steps)
    assert first and not first & second


def test_a_leading_article_does_not_stop_a_known_topic_matching(library_database):
    # Two live paths named the same prerequisite "Labour theory of value"
    # and "The labour theory of value".
    profile = reader_who_knows("labour theory of value")
    llm = ScriptedLLM("prerequisite: The labour theory of value | theory | essential\nprerequisite: Rent | concept | essential")
    path = service(library_database, llm).build_learning_path("the rate of profit", profile)

    assert path.already_known == ("The labour theory of value",)
    assert [s.name for s in path.steps] == ["Rent"]
