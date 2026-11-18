from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from praxis.reader_model import (
    AssessmentSource,
    InterestProfile,
    KnowledgeLevel,
    KnowledgeProfile,
    ReaderProfile,
    ReadingHistory,
)

INFERRED, STATED = AssessmentSource.INFERRED, AssessmentSource.USER_STATED
T0 = datetime(2026, 11, 18, 12, 0)


# --- KnowledgeProfile -------------------------------------------------------


def test_unknown_topic_has_no_knowledge():
    assert KnowledgeProfile().get_level("dialectics") is KnowledgeLevel.NONE


def test_topics_are_case_and_space_insensitive():
    knowledge = KnowledgeProfile()
    knowledge.update_level("  Surplus   Value ", KnowledgeLevel.INTRODUCTORY)

    assert knowledge.get_level("surplus value") is KnowledgeLevel.INTRODUCTORY


def test_empty_topic_is_rejected():
    with pytest.raises(ValueError):
        KnowledgeProfile().get_level("   ")


def test_inference_raises_level_and_counts_evidence():
    knowledge = KnowledgeProfile()
    knowledge.update_level("state", KnowledgeLevel.INTRODUCTORY)

    changed = knowledge.update_level("state", KnowledgeLevel.INTERMEDIATE)

    area = knowledge.areas["state"]
    assert changed
    assert (area.level, area.evidence, area.source) == (KnowledgeLevel.INTERMEDIATE, 2, INFERRED)


def test_inference_never_lowers_an_inferred_level():
    knowledge = KnowledgeProfile()
    knowledge.update_level("state", KnowledgeLevel.ADVANCED)

    changed = knowledge.update_level("state", KnowledgeLevel.INTRODUCTORY)

    assert not changed
    assert knowledge.get_level("state") is KnowledgeLevel.ADVANCED


def test_user_correction_overrides_inference_in_either_direction():
    knowledge = KnowledgeProfile()
    knowledge.update_level("state", KnowledgeLevel.ADVANCED)

    assert knowledge.update_level("state", KnowledgeLevel.INTRODUCTORY, STATED)
    assert knowledge.get_level("state") is KnowledgeLevel.INTRODUCTORY
    assert knowledge.areas["state"].source is STATED


def test_inference_cannot_override_a_user_correction():
    knowledge = KnowledgeProfile()
    knowledge.update_level("state", KnowledgeLevel.NONE, STATED)

    assert not knowledge.update_level("state", KnowledgeLevel.ADVANCED)
    assert knowledge.get_level("state") is KnowledgeLevel.NONE


def test_removed_assessment_returns_to_unknown():
    knowledge = KnowledgeProfile()
    knowledge.update_level("state", KnowledgeLevel.ADVANCED)

    assert knowledge.remove("STATE")
    assert not knowledge.remove("state")
    assert knowledge.get_level("state") is KnowledgeLevel.NONE


def test_blind_spots_are_topics_below_required_level_in_order():
    knowledge = KnowledgeProfile()
    knowledge.update_level("commodity", KnowledgeLevel.INTERMEDIATE)
    knowledge.update_level("value", KnowledgeLevel.INTRODUCTORY)

    topics = ["value", "commodity", "surplus value"]
    assert knowledge.identify_blind_spots(topics) == ["surplus value"]
    assert knowledge.identify_blind_spots(topics, KnowledgeLevel.INTERMEDIATE) == [
        "value",
        "surplus value",
    ]


# --- InterestProfile --------------------------------------------------------


def test_interests_accumulate_and_rank():
    interests = InterestProfile()
    interests.add("imperialism")
    interests.add("labour", 2.0)
    interests.add("Imperialism", 2.0)

    assert interests.top(2) == ["imperialism", "labour"]


def test_removed_interest_is_not_reinferred_but_can_be_restated():
    interests = InterestProfile()
    interests.add("religion")
    interests.remove("religion")

    interests.add("religion")
    assert interests.top() == []

    interests.add("religion", stated=True)
    assert interests.top() == ["religion"]


# --- ReadingHistory ---------------------------------------------------------


def test_progress_only_moves_forward():
    history, doc = ReadingHistory(), uuid4()
    history.record(doc, "Manifesto", 30, 100, T0)

    record = history.record(doc, "Manifesto", 5, 100, T0 + timedelta(minutes=1))

    assert record.furthest_paragraph == 30
    assert record.progress == 0.3
    assert record.last_read == T0 + timedelta(minutes=1)
    assert not record.completed


def test_reaching_last_paragraph_completes_the_text():
    history, doc = ReadingHistory(), uuid4()
    history.record(doc, "Letter", 64, 64, T0)

    assert [r.title for r in history.completed()] == ["Letter"]


def test_recent_orders_by_last_read():
    history = ReadingHistory()
    history.record(uuid4(), "Old", 1, 10, T0)
    history.record(uuid4(), "New", 1, 10, T0 + timedelta(days=1))

    assert [r.title for r in history.recent()] == ["New", "Old"]


def test_document_without_paragraphs_has_zero_progress():
    record = ReadingHistory().record(uuid4(), "Empty", 0, 0, T0)

    assert record.progress == 0.0 and not record.completed


# --- ReaderProfile ----------------------------------------------------------


def test_new_profile_is_sparse_until_anything_is_known():
    profile = ReaderProfile()
    assert profile.is_sparse

    profile.interests.add("labour")
    assert not profile.is_sparse
