"""The recommendation prompt and the parsing of the model's ranking (F07)."""

from praxis.agent.prompts import MAX_RECOMMENDATIONS, PromptBuilder
from praxis.reader_model import KnowledgeLevel, ReaderProfile
from praxis.reading.recommendations import ExternalSuggestion, parse_recommendations

CANDIDATES = [
    ("[1] Lenin, “A Letter to American Workingmen” (1918)", "Matching passages: 3"),
    ("[2] Marx, “The Eighteenth Brumaire” (1852)", "Matching passages: 1"),
]


def test_prompt_lists_the_topic_and_numbered_candidates():
    prompt = PromptBuilder().build_recommendation_prompt("imperialism", CANDIDATES)

    assert prompt.user.startswith("Topic: imperialism")
    assert "[1] Lenin" in prompt.user and "Matching passages: 1" in prompt.user
    assert "recommend: [n]" in prompt.system
    assert "About the reader" not in prompt.system
    # The CLI prints progress itself; a live run repeated it in every reason.
    assert "do not restate it in the reason" in prompt.system


def test_prompt_describes_the_reader_only_when_something_is_known():
    profile = ReaderProfile()
    profile.knowledge.update_level("class struggle", KnowledgeLevel.INTRODUCTORY)

    prompt = PromptBuilder().build_recommendation_prompt("imperialism", CANDIDATES, profile)

    assert "About the reader" in prompt.system
    assert "class struggle" in prompt.system


def test_prompt_without_candidates_says_the_library_has_nothing():
    prompt = PromptBuilder().build_recommendation_prompt("imperialism", [])

    assert "No text in the library matched" in prompt.user


def test_parse_reads_ranked_lines_and_external_suggestions():
    reply = """\
recommend: [2] | Intermediate | Analyses the state after 1848.
- recommend: [1] | introductory | Short and direct.
external: Imperialism, the Highest Stage of Capitalism | V. I. Lenin | The standard text.
"""
    parsed = parse_recommendations(reply, candidates=2)

    assert parsed.ranked == (
        (2, "intermediate", "Analyses the state after 1848."),
        (1, "introductory", "Short and direct."),
    )
    assert parsed.external == (
        ExternalSuggestion("Imperialism, the Highest Stage of Capitalism", "V. I. Lenin", "The standard text."),
    )
    assert parsed.unknown == ()


def test_parse_reports_invented_numbers_and_keeps_each_candidate_once():
    reply = "recommend: [1] | advanced | First.\nrecommend: [7] | introductory | No such.\nrecommend: [1] | introductory | Again."

    parsed = parse_recommendations(reply, candidates=2)

    assert parsed.ranked == ((1, "advanced", "First."),)
    assert parsed.unknown == (7,)


def test_parse_drops_an_unknown_difficulty_but_keeps_the_line():
    parsed = parse_recommendations("recommend: [1] | very hard | Dense.", candidates=1)

    assert parsed.ranked == ((1, None, "Dense."),)


def test_parse_caps_the_number_of_recommendations():
    reply = "\n".join(f"recommend: [{n}] | introductory | r{n}" for n in range(1, 9))

    parsed = parse_recommendations(reply, candidates=8)

    assert len(parsed.ranked) == MAX_RECOMMENDATIONS


def test_parse_returns_none_for_a_reply_in_another_form():
    assert parse_recommendations("I would suggest reading Lenin first.", candidates=2) is None


def test_a_reply_recommending_nothing_is_still_readable():
    parsed = parse_recommendations("external: Capital | Karl Marx | The library lacks it.", candidates=2)

    assert parsed is not None
    assert parsed.ranked == ()
