"""NewsSummaryService and the event summary prompt (F01, SD03)."""

from datetime import date

from conftest import ScriptedLLM

from praxis.agent.prompts import PromptBuilder
from praxis.documents import NewsArticle
from praxis.llm import LLMError
from praxis.news.events import Event, Grouping, SummaryStatus
from praxis.news.summary import NewsSummaryService, read_summary


def report(title, outlet, text):
    return NewsArticle(title=title, author="Staff", outlet=outlet, text=text,
                       publication_date=date(2026, 11, 22), source_url=f"https://example.org/{outlet}")


EVENT = Event((
    report("Fire at Indonesian candy factory leaves 3 dead", "Wire A", "Three workers died."),
    report("Dozens missing after factory fire in Indonesia", "Wire B", "Officials said 30 are missing."),
), Grouping.CONFIDENT)

REPLY = """\
title: Deadly fire at Indonesian sweets factory
summary: A fire at a confectionery factory in Indonesia killed three workers [1]. Officials said dozens are missing [2].
category: labour, society, sport
same event: yes
"""


def test_prompt_numbers_the_reports_with_outlet_and_date():
    prompt = PromptBuilder().build_event_summary_prompt([
        ("Wire A", "2026-11-22", "Fire kills three", "Three workers died."),
        ("Wire B", "undated", "Dozens missing", ""),
    ])
    assert "[1] Wire A, 2026-11-22\nHeadline: Fire kills three\nThree workers died." in prompt.user
    assert "[2] Wire B, undated\nHeadline: Dozens missing\n(no summary in the feed)" in prompt.user
    assert "Do not adopt one outlet's framing" in prompt.system
    assert "do not pick one" in prompt.system


def test_a_cited_summary_fills_the_card():
    llm = ScriptedLLM(REPLY)
    outcome = NewsSummaryService(llm).summarize(EVENT)
    event = outcome.event
    assert event.summary_status is SummaryStatus.SUMMARIZED
    assert event.headline == "Deadly fire at Indonesian sweets factory"
    assert event.summary.endswith("Officials said dozens are missing [2].")
    assert event.categories == ("labour", "society")  # "sport" is not a category
    assert event.id == EVENT.id
    assert outcome.tokens_used == 15
    assert "Wire B" in llm.prompts[0].user


def test_reports_judged_not_one_event_are_marked_uncertain():
    event = read_summary(EVENT, REPLY.replace("same event: yes", "same event: no | [2] is a different fire"))
    assert event.grouping is Grouping.UNCERTAIN
    assert event.note == "The model judged that these reports are not all about one event: [2] is a different fire."
    assert event.is_summarized


def test_an_uncited_summary_falls_back_to_headlines():
    event = read_summary(EVENT, "title: Fire\nsummary: A factory burned.\nsame event: yes")
    assert event.summary_status is SummaryStatus.HEADLINES_ONLY
    assert event.summary == ""
    assert event.note == "The summary cited none of the reports."


def test_a_summary_citing_a_missing_report_falls_back_to_headlines():
    event = read_summary(EVENT, "summary: A factory burned [3].")
    assert event.summary_status is SummaryStatus.HEADLINES_ONLY
    assert "[3], which is not among the reports" in event.note


def test_a_reply_without_a_summary_falls_back_to_headlines():
    event = read_summary(EVENT, "The reports describe a fire.")
    assert event.summary_status is SummaryStatus.HEADLINES_ONLY


def test_model_failure_falls_back_to_headlines():
    outcome = NewsSummaryService(ScriptedLLM(LLMError("rate limited"))).summarize(EVENT)
    assert outcome.event.summary_status is SummaryStatus.HEADLINES_ONLY
    assert "rate limited" in outcome.event.note


def test_without_a_model_the_card_shows_headlines():
    outcome = NewsSummaryService(None).summarize(EVENT)
    assert outcome.event.summary_status is SummaryStatus.HEADLINES_ONLY
