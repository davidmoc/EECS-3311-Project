"""Parsing and checking the Marxist analysis (F11)."""

from praxis.agent.corpus import ResearchCorpus
from praxis.agent.prompts import MAX_CONCEPTS, PromptBuilder
from praxis.documents import Book
from praxis.research.analysis import (
    AnalysisItem,
    AnalysisItemKind,
    AnalysisStatus,
    MaterialistAnalysis,
    check_analysis,
    parse_analysis,
    parse_concepts,
)


def test_concepts_are_read_once_each_and_capped():
    reply = "\n".join([
        "concept: the state | state, executive, committee | The evidence shows the state siding with capital.",
        "1. concept: wage labour | wages, subsistence |",
        "concept: The State | duplicate | again",
        *[f"concept: c{n} | k{n} | r{n}" for n in range(6)],
    ])
    concepts = parse_concepts(reply)

    assert concepts[0].name == "the state"
    assert concepts[0].keywords == "state, executive, committee"
    assert concepts[1].reason == ""
    assert len(concepts) == MAX_CONCEPTS
    assert parse_concepts("The state is relevant.") == []


REPLY = """\
condition: class | Workers fought while the bourgeoisie held back [2].
application: the state | The Manifesto's committee of the bourgeoisie explains the peace with the monarchy [3, 1].
claim: supported | The bourgeoisie chose order over revolution [1, 2].
claim: The workers alone pressed the revolution [2].
alternative: The peace may reflect military weakness rather than class fear [1].
limit: The evidence says nothing about the peasants.
"""


def test_analysis_lines_are_parsed_with_labels_and_evidence():
    parsed = parse_analysis(REPLY)

    condition, application, supported, unlabelled, alternative = parsed.items
    assert (condition.label, condition.text, condition.evidence) == (
        "class", "Workers fought while the bourgeoisie held back.", (2,))
    assert (application.label, application.evidence) == ("the state", (3, 1))
    assert supported.label == "supported" and not supported.is_tentative
    assert unlabelled.label == "tentative" and unlabelled.is_tentative
    assert alternative.text == "The peace may reflect military weakness rather than class fear."
    assert parsed.limits == ("The evidence says nothing about the peasants.",)


def test_an_analysis_in_another_form_is_unreadable():
    assert parse_analysis("The revolution failed because of class fear.") is None


PURPOSES = {1: "evidence", 2: "evidence", 3: "theory"}


def test_an_application_needs_theory_and_evidence():
    items = (
        AnalysisItem(AnalysisItemKind.APPLICATION, "both", (3, 1), "state"),
        AnalysisItem(AnalysisItemKind.APPLICATION, "theory only", (3,), "state"),
        AnalysisItem(AnalysisItemKind.APPLICATION, "evidence only", (1, 2), "state"),
    )
    kept, dropped = check_analysis(items, PURPOSES, {1, 2, 3})

    assert [i.text for i in kept] == ["both"]
    assert dropped == 2


def test_a_condition_must_rest_on_evidence_and_unknown_citations_are_removed():
    items = (
        AnalysisItem(AnalysisItemKind.CONDITION, "from theory", (3,), "class"),
        AnalysisItem(AnalysisItemKind.CLAIM, "partly invented", (2, 9), "supported"),
        AnalysisItem(AnalysisItemKind.ALTERNATIVE, "invented", (9,)),
    )
    kept, dropped = check_analysis(items, PURPOSES, {1, 2, 3})

    assert kept == [AnalysisItem(AnalysisItemKind.CLAIM, "partly invented", (2,), "supported")]
    assert dropped == 2


def test_an_analysis_with_only_tentative_claims_is_tentative():
    tentative = AnalysisItem(AnalysisItemKind.CLAIM, "t", (1,), "tentative")
    supported = AnalysisItem(AnalysisItemKind.CLAIM, "s", (1, 2), "supported")

    assert MaterialistAnalysis("x", AnalysisStatus.ANALYSED, items=(tentative,)).is_tentative
    assert not MaterialistAnalysis("x", AnalysisStatus.ANALYSED, items=(tentative, supported)).is_tentative


def test_prompts_carry_framework_findings_and_grouped_passages():
    book = Book(title="Manifesto", author="Marx", text="The executive of the modern state is a committee.")
    corpus = ResearchCorpus()
    source = corpus.add_passage(book, book.paragraph(1))
    builder = PromptBuilder()

    concepts = builder.build_concept_prompt("1848", [source], framework="Lenin on the state")
    assert "framework: Lenin on the state" in concepts.user and "[1] Marx" in concepts.user
    assert "No evidence passages" in builder.build_concept_prompt("1848", []).user

    analysis = builder.build_analysis_prompt(
        "1848", corpus, {1: "theory"}, established=["relation: class | x [1]"]
    )
    assert "Retrieved for theoretical background" in analysis.user
    assert "- relation: class | x [1]" in analysis.user
    assert "application: <concept>" in analysis.system


def test_citations_removed_at_the_end_leave_no_stray_commas():
    # A live analysis printed "socialism)," and "independence,,".
    parsed = parse_analysis(
        "claim: supported | movements (Chartism, socialism), [11, 5]\n"
        "condition: production | superseding of small masters and family independence,, [13, 1]"
    )

    assert [i.text for i in parsed.items] == [
        "movements (Chartism, socialism)",
        "superseding of small masters and family independence",
    ]


def test_a_headed_alternative_or_limit_is_split_at_the_bar():
    # A live analysis headed its alternatives and limits "label | text",
    # which were printed with the bar.
    parsed = parse_analysis(
        "alternative: reformist reading of the Poor Law | a response to fiscal crisis [3]\n"
        "limit: commodity fetishism | the passages offer little on it"
    )

    alternative = parsed.items[0]
    assert (alternative.label, alternative.text) == ("reformist reading of the Poor Law", "a response to fiscal crisis")
    assert parsed.limits == ("commodity fetishism: the passages offer little on it",)


def test_brackets_holding_only_citations_are_removed_with_them():
    # A live analysis printed "machine (,) explains" and "conservative  applied".
    parsed = parse_analysis(
        "application: the state | the State as a machine ([23], [31]) explains it [7].\n"
        "application: petty bourgeoisie | petty traders are conservative [11] applied to 1848 [5]."
    )

    assert [i.text for i in parsed.items] == [
        "the State as a machine explains it.",
        "petty traders are conservative applied to 1848.",
    ]
