"""Parsing the historical-context plan and account (F09)."""

from uuid import uuid4

from praxis.agent.corpus import ResearchCorpus, Source
from praxis.agent.prompts import MAX_HISTORY_SEARCHES, PromptBuilder
from praxis.documents import Book, Citation, Passage
from praxis.research.history import (
    HistoryItem,
    HistoryItemKind,
    check_items,
    parse_history,
    parse_history_plan,
    suggested_readings,
)


def test_plan_reads_scope_and_searches():
    plan = parse_history_plan(
        "scope: focused |\nsearch: origins | feudal estates, guilds\n- search: 1848 | March revolution Berlin"
    )

    assert not plan.too_broad
    assert plan.narrower == ()
    assert plan.searches == (("origins", "feudal estates, guilds"), ("1848", "March revolution Berlin"))


def test_plan_can_ask_to_narrow_the_topic():
    plan = parse_history_plan("scope: too broad | the 1848 revolutions; the Paris Commune ; ")

    assert plan.too_broad
    assert plan.narrower == ("the 1848 revolutions", "the Paris Commune")
    assert plan.searches == ()


def test_plan_caps_searches_and_rejects_other_forms():
    plan = parse_history_plan("\n".join(f"search: s{n} | k{n}" for n in range(9)))

    assert len(plan.searches) == MAX_HISTORY_SEARCHES
    assert parse_history_plan("Search the library for 1848.") is None


REPLY = """\
overview: The German bourgeoisie gained ground and then made peace with the monarchy [1, 2].
origin: The workers of Vienna and Berlin fought on the barricades [2].
stage: 1848 | The revolution spread from Paris across Germany [1].
turning point: The bourgeoisie made peace with the monarchy [1].
interpretation: Engels holds that the liberals feared the workers more than the old order [2].
continuity: The monarchy kept the army [3]
gap: The passages say nothing about the peasants.
"""


def test_account_is_parsed_with_citations_moved_to_evidence():
    parsed = parse_history(REPLY)

    assert parsed.overview == "The German bourgeoisie gained ground and then made peace with the monarchy."
    assert parsed.overview_evidence == (1, 2)
    stage = next(i for i in parsed.items if i.kind is HistoryItemKind.STAGE)
    assert (stage.when, stage.text, stage.evidence) == ("1848", "The revolution spread from Paris across Germany.", (1,))
    turning = next(i for i in parsed.items if i.kind is HistoryItemKind.TURNING_POINT)
    assert turning.when == "undated"
    assert parsed.gaps == ("The passages say nothing about the peasants.",)
    assert [i.kind for i in parsed.items].count(HistoryItemKind.INTERPRETATION) == 1


def test_account_in_another_form_is_unreadable():
    assert parse_history("The revolution failed because the bourgeoisie was weak.") is None


def test_items_are_capped_per_kind():
    parsed = parse_history("\n".join(f"origin: cause {n} [1]" for n in range(10)))

    assert len(parsed.items) == 6


def test_items_citing_no_retrieved_source_are_dropped():
    items = (
        HistoryItem(HistoryItemKind.ORIGIN, "a", (1, 9)),
        HistoryItem(HistoryItemKind.STAGE, "b", (9,), "1848"),
        HistoryItem(HistoryItemKind.CONTINUITY, "c", ()),
    )
    kept, dropped = check_items(items, {1, 2})

    assert kept == [HistoryItem(HistoryItemKind.ORIGIN, "a", (1,))]
    assert dropped == 2


def source(number, document_id, title, locator):
    return Source(number, Passage(uuid4(), document_id, "text", locator),
                  Citation(document_id, title, "Engels", locator, "text"))


def test_suggested_readings_are_the_cited_texts_most_cited_first():
    a, b = uuid4(), uuid4()
    cited = (source(1, a, "A", "¶3"), source(2, b, "B", "¶7"), source(3, b, "B", "¶9"))

    readings = suggested_readings(cited)

    assert [(r.title, r.cited, r.start) for r in readings] == [("B", 2, "¶7"), ("A", 1, "¶3")]


def test_prompts_carry_the_topic_and_grouped_passages():
    builder = PromptBuilder()
    assert builder.build_history_plan_prompt("1848 in Germany").user == "Topic: 1848 in Germany"

    book = Book(title="Revolution", author="Engels", text="In 1848 the revolution broke out in Paris.")
    corpus = ResearchCorpus()
    corpus.add_passage(book, book.paragraph(1))
    prompt = builder.build_history_prompt("1848", corpus, {1: "history"})

    assert "Retrieved for historical development" in prompt.user
    assert "[1] Engels, “Revolution”, ¶1" in prompt.user
    assert "turning point: <when>" in prompt.system


def test_account_rules_ask_for_one_chronological_sequence():
    # A live account listed every stage, then every turning point, and gave
    # some events twice, once as each.
    system = PromptBuilder().build_history_prompt("1848", _one_passage_corpus(), {1: "history"}).system

    assert "one sequence in chronological order, mixing the two kinds" in system
    assert "never list one event as both" in system


def test_chronology_keeps_the_model_order_across_kinds():
    parsed = parse_history("stage: March 1848 | Risings [1]\nturning point: October 1848 | Vienna falls [1]\nstage: 1849 | Reaction [1]")

    assert [i.when for i in parsed.items if i.kind.is_dated] == ["March 1848", "October 1848", "1849"]


def _one_passage_corpus():
    book = Book(title="Revolution", author="Engels", text="In 1848 the revolution broke out in Paris.")
    corpus = ResearchCorpus()
    corpus.add_passage(book, book.paragraph(1))
    return corpus
