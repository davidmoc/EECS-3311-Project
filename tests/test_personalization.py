"""PersonalizationService and RequestPreferences (F14, UC14)."""

from praxis.persistence import Database, SQLReaderProfileRepository
from praxis.reader_model import AssessmentSource, ExplanationDepth, KnowledgeLevel, ReaderProfile
from praxis.reader_model.personalization import (
    NOTHING_ON_TOPIC,
    PersonalizationService,
    RequestPreferences,
    topic_words,
)
from praxis.reader_model.service import ReaderProfileService


def profile_knowing(*areas, interests=()):
    profile = ReaderProfile()
    for topic, level, source in areas:
        profile.knowledge.update_level(topic, level, source)
    for interest in interests:
        profile.interests.add(interest)
    return profile


STATED = AssessmentSource.USER_STATED
INFERRED = AssessmentSource.INFERRED


def test_topic_words_drop_filler_and_plurals():
    assert topic_words("The history of the Paris Communes") == {"history", "paris", "commune"}
    assert topic_words("Marx's class analysis") == {"marx", "class", "analysis"}


def test_knowledge_of_the_requests_topic_comes_first():
    profile = profile_knowing(
        ("dialectics", KnowledgeLevel.ADVANCED, STATED),
        ("surplus value", KnowledgeLevel.INTRODUCTORY, STATED),
        ("value form", KnowledgeLevel.INTERMEDIATE, INFERRED),
    )
    context = PersonalizationService.personalize_prompt(profile, "What is surplus value?")

    lines = context.splitlines()
    assert lines[0] == "On this topic:"
    assert lines[1:3] == [
        "- Probably at intermediate level in value form (inferred from reading)",
        "- Says they are at introductory level in surplus value",
    ]
    assert lines[3:5] == ["Other knowledge:", "- Says they are at advanced level in dialectics"]


def test_nothing_recorded_on_the_topic_is_said_so():
    profile = profile_knowing(("dialectics", KnowledgeLevel.ADVANCED, STATED), interests=("imperialism",))
    context = PersonalizationService.personalize_prompt(profile, "the Paris Commune")

    assert NOTHING_ON_TOPIC in context
    assert "- Says they are at advanced level in dialectics" in context
    assert "- Interested in: imperialism" in context


def test_without_a_topic_all_knowledge_is_listed_as_before():
    profile = profile_knowing(("dialectics", KnowledgeLevel.ADVANCED, STATED))
    context = PersonalizationService.personalize_prompt(profile)

    assert context.splitlines()[0] == "- Says they are at advanced level in dialectics"
    assert NOTHING_ON_TOPIC not in context


def test_a_sparse_or_switched_off_profile_stays_general():
    assert PersonalizationService.personalize_prompt(ReaderProfile(), "value") is None
    assert PersonalizationService.personalize_prompt(None, "value") is None
    profile = profile_knowing(("value", KnowledgeLevel.ADVANCED, STATED))
    profile.personalization_enabled = False
    assert PersonalizationService.personalize_prompt(profile, "value") is None


def test_preferences_change_a_copy_for_one_request_only():
    database = Database()
    profiles = ReaderProfileService(SQLReaderProfileRepository(database))
    profiles.correct_knowledge_assessment("value", KnowledgeLevel.ADVANCED)
    service = PersonalizationService(profiles)

    brief = service.profile_for(RequestPreferences(depth=ExplanationDepth.BRIEF))
    general = service.profile_for(RequestPreferences(personalized=False))

    assert brief.explanation_depth is ExplanationDepth.BRIEF
    assert brief.personalization_enabled
    assert not general.personalization_enabled
    assert general.explanation_depth is ExplanationDepth.STANDARD
    stored = profiles.get_profile()
    assert (stored.explanation_depth, stored.personalization_enabled) == (ExplanationDepth.STANDARD, True)
    assert service.profile_for() == stored
    database.close()


def test_a_request_cannot_turn_personalization_back_on():
    profile = ReaderProfile(personalization_enabled=False)
    assert not RequestPreferences(personalized=True).apply(profile).personalization_enabled


def test_explanation_depth_defaults_to_standard():
    assert PersonalizationService.determine_explanation_depth(None) is ExplanationDepth.STANDARD
    profile = ReaderProfile(explanation_depth=ExplanationDepth.DETAILED)
    assert PersonalizationService.determine_explanation_depth(profile) is ExplanationDepth.DETAILED
