"""RecommendationService (F07, UC07, SD05)."""

from datetime import datetime

import pytest
from conftest import ScriptedLLM

from praxis.documents import NewsArticle
from praxis.llm import LLMError
from praxis.persistence import SQLDocumentRepository
from praxis.reader_model import KnowledgeLevel, ReaderProfile
from praxis.reading.recommendations import (
    NO_CANDIDATES_WARNING,
    NO_LLM_WARNING,
    PERSONALIZATION_OFF_WARNING,
    SPARSE_PROFILE_WARNING,
    UNREADABLE_WARNING,
    ReadingStatus,
    RecommendationError,
    RecommendationService,
)
from praxis.tools import PassageSearchTool, ToolManager


def service(database, llm=None):
    tools = ToolManager()
    tools.register_tool(PassageSearchTool(SQLDocumentRepository(database)))
    return RecommendationService(tools, llm)


def documents(database):
    found = {d.title: d for d in SQLDocumentRepository(database).list_all()}
    return found["The Communist Manifesto"], found["Revolution and Counter-Revolution in Germany"]


def known_reader():
    profile = ReaderProfile()
    profile.knowledge.update_level("class struggle", KnowledgeLevel.INTRODUCTORY)
    return profile


# "bourgeoisie" is in both passages of the Revolution text and one of the
# Manifesto's, so the Revolution text is candidate [1].


def test_without_a_model_texts_are_ranked_by_matching_passages(library_database):
    result = service(library_database).recommend_readings("bourgeoisie")

    titles = [r.document.title for r in result.recommendations]
    assert titles == ["Revolution and Counter-Revolution in Germany", "The Communist Manifesto"]
    assert result.recommendations[0].reason == "2 passages match the topic."
    assert result.recommendations[1].reason == "1 passage matches the topic."
    assert not result.ranked_by_model
    assert NO_LLM_WARNING in result.warnings


def test_each_recommendation_carries_where_the_topic_comes_up(library_database):
    result = service(library_database).recommend_readings("bourgeoisie")

    revolution = result.recommendations[0]
    assert [c.locator for c in revolution.passages] == ["¶1", "¶2"]
    assert "bourgeoisie" in revolution.passages[0].quoted_text


def test_model_ranking_and_reasons_are_used(library_database):
    llm = ScriptedLLM(
        "recommend: [2] | introductory | States the theory briefly.\n"
        "recommend: [1] | intermediate | Shows it in 1848.\n"
        "external: Capital, Volume I | Karl Marx | The library lacks it."
    )
    result = service(library_database, llm).recommend_readings("bourgeoisie")

    assert [r.document.title for r in result.recommendations] == [
        "The Communist Manifesto", "Revolution and Counter-Revolution in Germany",
    ]
    assert result.recommendations[0].reason == "States the theory briefly."
    assert result.recommendations[0].difficulty == "introductory"
    assert result.external[0].title == "Capital, Volume I"
    assert result.ranked_by_model
    assert result.tokens_used == 15
    prompt = llm.prompts[0].user
    assert prompt.startswith("Topic: bourgeoisie")
    assert "[1] Friedrich Engels, “Revolution and Counter-Revolution in Germany”" in prompt
    assert "Matching passages: 2" in prompt


def test_texts_the_model_leaves_out_are_counted(library_database):
    llm = ScriptedLLM("recommend: [1] | intermediate | The fuller account.")
    result = service(library_database, llm).recommend_readings("bourgeoisie")

    assert len(result.recommendations) == 1
    assert result.passed_over == 1


def test_an_invented_candidate_is_ignored_with_a_warning(library_database):
    llm = ScriptedLLM("recommend: [5] | introductory | No such text.\nrecommend: [1] | advanced | Real.")
    result = service(library_database, llm).recommend_readings("bourgeoisie")

    assert len(result.recommendations) == 1
    assert any("[5]" in w and "not among the texts found" in w for w in result.warnings)


def test_unreadable_ranking_falls_back_to_matches(library_database):
    llm = ScriptedLLM("You should read the Manifesto.")
    result = service(library_database, llm).recommend_readings("bourgeoisie")

    assert len(result.recommendations) == 2
    assert not result.ranked_by_model
    assert UNREADABLE_WARNING in result.warnings
    assert result.tokens_used == 15


def test_model_failure_falls_back_to_matches(library_database):
    result = service(library_database, ScriptedLLM(LLMError("timeout"))).recommend_readings("bourgeoisie")

    assert len(result.recommendations) == 2
    assert any("timeout" in w for w in result.warnings)


def test_finished_texts_go_last(library_database):
    manifesto, _ = documents(library_database)
    profile = known_reader()
    profile.history.record(manifesto.id, manifesto.title, 3, 3, datetime(2026, 11, 1))
    llm = ScriptedLLM(
        "recommend: [2] | introductory | Short.\nrecommend: [1] | intermediate | Longer."
    )
    result = service(library_database, llm).recommend_readings("bourgeoisie", profile)

    assert [r.status for r in result.recommendations] == [ReadingStatus.UNREAD, ReadingStatus.COMPLETED]
    assert result.recommendations[1].document.title == "The Communist Manifesto"
    assert "Reader: has finished it" in llm.prompts[0].user


def test_progress_through_a_text_is_reported(library_database):
    _, revolution = documents(library_database)
    profile = known_reader()
    profile.history.record(revolution.id, revolution.title, 1, 2, datetime(2026, 11, 1))
    result = service(library_database).recommend_readings("bourgeoisie", profile)

    assert result.recommendations[0].status is ReadingStatus.IN_PROGRESS
    assert result.recommendations[0].progress == 0.5


def test_a_sparse_profile_is_not_presented_as_personal(library_database):
    llm = ScriptedLLM("recommend: [1] | introductory | Good.")
    result = service(library_database, llm).recommend_readings("bourgeoisie", ReaderProfile())

    assert not result.personalized
    assert SPARSE_PROFILE_WARNING in result.warnings
    assert "About the reader" not in llm.prompts[0].system


def test_a_known_reader_gets_personalized_ranking(library_database):
    llm = ScriptedLLM("recommend: [1] | introductory | Builds on class struggle.")
    result = service(library_database, llm).recommend_readings("bourgeoisie", known_reader())

    assert result.personalized
    assert SPARSE_PROFILE_WARNING not in result.warnings
    assert "class struggle" in llm.prompts[0].system


def test_personalization_off_ignores_history(library_database):
    manifesto, _ = documents(library_database)
    profile = known_reader()
    profile.personalization_enabled = False
    profile.history.record(manifesto.id, manifesto.title, 3, 3, datetime(2026, 11, 1))
    llm = ScriptedLLM("recommend: [2] | introductory | Short.")
    result = service(library_database, llm).recommend_readings("bourgeoisie", profile)

    assert result.recommendations[0].status is ReadingStatus.UNKNOWN
    assert not result.personalized
    assert PERSONALIZATION_OFF_WARNING in result.warnings
    assert "Reader:" not in llm.prompts[0].user


def test_news_is_not_recommended(library_database):
    SQLDocumentRepository(library_database).save(NewsArticle(
        title="Bourgeoisie protests", author="", outlet="Example News",
        text="The bourgeoisie of the city protested against the new tax on trade.",
    ))
    result = service(library_database).recommend_readings("bourgeoisie")

    assert all(r.document.kind != "news" for r in result.recommendations)


def test_no_matching_text_may_still_get_external_suggestions(library_database):
    llm = ScriptedLLM("external: Imperialism, the Highest Stage of Capitalism | V. I. Lenin | The classic.")
    result = service(library_database, llm).recommend_readings("finance capital")

    assert result.recommendations == ()
    assert result.external[0].author == "V. I. Lenin"
    assert NO_CANDIDATES_WARNING in result.warnings
    assert "No text in the library matched" in llm.prompts[0].user


def test_an_empty_topic_is_refused(library_database):
    with pytest.raises(RecommendationError):
        service(library_database).recommend_readings("   ")


def test_next_readings_come_from_the_strongest_interests(library_database):
    profile = ReaderProfile()
    profile.interests.add("bourgeoisie", 3)
    profile.interests.add("wage labour", 1)
    result = service(library_database).recommend_next(profile)

    assert result.topic == "bourgeoisie, wage labour"
    assert {r.document.title for r in result.recommendations} == {
        "The Communist Manifesto", "Revolution and Counter-Revolution in Germany",
    }


def test_next_readings_need_an_interest(library_database):
    with pytest.raises(RecommendationError, match="interests"):
        service(library_database).recommend_next(ReaderProfile())


def test_next_readings_need_personalization(library_database):
    profile = ReaderProfile()
    profile.interests.add("bourgeoisie")
    profile.personalization_enabled = False
    with pytest.raises(RecommendationError, match="Personalization is off"):
        service(library_database).recommend_next(profile)


def test_texts_tagged_with_the_topic_come_before_word_matches(library_database):
    repository = SQLDocumentRepository(library_database)
    manifesto, _ = documents(library_database)
    manifesto.topics = ("bourgeoisie",)
    repository.save(manifesto)

    result = service(library_database).recommend_readings("Bourgeoisie")

    # The Revolution text has more matching passages, but is not tagged.
    assert result.recommendations[0].document.title == "The Communist Manifesto"
