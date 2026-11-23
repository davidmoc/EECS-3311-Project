"""Reading the model's choice of traditions and its comparison (F12)."""

import pytest

from praxis.agent.corpus import ResearchCorpus
from praxis.agent.prompts import MAX_TRADITIONS, PromptBuilder
from praxis.documents import Book
from praxis.reading.traditions import (
    Perspective,
    StatementKind,
    Tradition,
    authored_by,
    check_comparison,
    parse_tradition_comparison,
    parse_traditions,
)


def test_traditions_are_read_with_marxism_first_and_each_author_once():
    parsed = parse_traditions(
        "perspective: Anarchism | Peter Kropotkin | free communism, mutual aid | Rejects the state.\n"
        "- **perspective**: Marxism | Karl Marx, Friedrich Engels | dictatorship of the proletariat | The platform's own.\n"
        "perspective: Anarcho-syndicalism | Peter Kropotkin, none | general strike | Unions over parties.\n"
        "perspective: anarchism | Someone | duplicate | ignored\n"
        "Some prose the model added."
    )

    assert [t.name for t in parsed.traditions] == ["Marxism", "Anarchism", "Anarcho-syndicalism"]
    assert parsed.traditions[0].representatives == ("Karl Marx", "Friedrich Engels")
    assert parsed.traditions[1].keywords == "free communism, mutual aid"
    assert parsed.traditions[1].relevance == "Rejects the state."
    # Kropotkin already represents anarchism; "none" is not an author.
    assert parsed.traditions[2].representatives == ()
    assert parsed.none_reason == ""


def test_no_other_tradition_is_read_with_its_reason():
    parsed = parse_traditions(
        "perspective: Marxism | Karl Marx | value, commodity | Central.\n"
        "none: Other traditions accept the labour theory of value here."
    )

    assert [t.name for t in parsed.traditions] == ["Marxism"]
    assert parsed.none_reason == "Other traditions accept the labour theory of value here."


def test_traditions_are_capped_and_a_reply_in_another_form_is_unreadable():
    lines = "\n".join(f"perspective: Tradition {n} | none | words | why" for n in range(8))
    assert len(parse_traditions(lines).traditions) == MAX_TRADITIONS
    assert parse_traditions("Marxism and anarchism disagree about the state.") is None


def test_comparison_lines_are_parsed_by_kind_and_tradition():
    parsed = parse_tradition_comparison(
        "position: Marxism | The proletariat must take state power [1].\n"
        "conditions: Anarchism | Grew among artisans and peasants [3].\n"
        "disagreement: Whether the state can serve the revolution [1, 3].\n"
        "assessment: Anarchism | Marxists call it utopian [2].\n"
        "position: missing its tradition [1]\n"
        "gap: Nothing on the Paris Commune."
    )

    kinds = [(s.kind, s.tradition, s.evidence) for s in parsed.statements]
    assert kinds == [
        (StatementKind.POSITION, "Marxism", (1,)),
        (StatementKind.CONDITIONS, "Anarchism", (3,)),
        (StatementKind.ASSESSMENT, "Anarchism", (2,)),
    ]
    assert parsed.statements[0].text == "The proletariat must take state power."
    assert [(d.text, d.evidence) for d in parsed.disagreements] == [
        ("Whether the state can serve the revolution.", (1, 3)),
    ]
    assert parsed.gaps == ("Nothing on the Paris Commune.",)
    assert parse_tradition_comparison("Marxism wants the state; anarchism does not.") is None


MARXISM = Perspective(Tradition("Marxism"), own=(1, 2))
ANARCHISM = Perspective(Tradition("Anarchism"), own=(3,))
SYNDICALISM = Perspective(Tradition("Syndicalism"), reported=(4,))


def check(reply):
    return check_comparison(parse_tradition_comparison(reply), (MARXISM, ANARCHISM, SYNDICALISM))


def test_a_disagreement_must_cite_two_traditions():
    statements, disagreements, dropped = check(
        "disagreement: Only Marxist passages [1, 2].\n"
        "disagreement: The state [2, 3]."
    )

    assert [d.evidence for d in disagreements] == [(2, 3)]
    assert dropped == 1


def test_statements_need_a_known_tradition_and_a_known_passage():
    statements, _, dropped = check(
        "position: Anarchism (Kropotkin) | Abolish the state at once [3, 9].\n"
        "position: Fabianism | Gradual reform [1].\n"
        "conditions: Marxism | Industrial England [9].\n"
        "assessment: Marxism | Marxism assesses itself [1]."
    )

    # "Anarchism (Kropotkin)" is matched to Anarchism; [9] was not retrieved.
    assert [(s.tradition, s.evidence) for s in statements] == [("Anarchism", (3,))]
    assert dropped == 3


def test_a_position_resting_only_on_others_is_not_in_its_own_words():
    statements, _, _ = check(
        "position: Syndicalism | The general strike [4].\n"
        "position: Anarchism | Free communism, as Marxists describe it [1].\n"
        "position: Marxism | The workers' state [1]."
    )

    assert [(s.tradition, s.in_own_words) for s in statements] == [
        ("Syndicalism", False), ("Anarchism", False), ("Marxism", True),
    ]


@pytest.mark.parametrize("representative, expected", [
    ("Karl Marx", True),
    ("Marx", True),
    ("Friedrich Engels", True),
    ("Peter Kropotkin", False),
    ("Marxen", False),
    ("", False),
])
def test_authors_are_matched_on_their_surname(representative, expected):
    book = Book(title="The Communist Manifesto", author="Karl Marx and Friedrich Engels", text="x")
    assert authored_by(book, representative) is expected


def test_comparison_prompt_groups_own_words_apart_from_others():
    corpus = ResearchCorpus()
    marx = Book(title="Manifesto", author="Karl Marx", text="The state is a committee of the bourgeoisie.")
    kropotkin = Book(title="Conquest of Bread", author="Peter Kropotkin", text="Bread for all.")
    own = corpus.add_passage(marx, marx.passages()[0])
    other = corpus.add_passage(kropotkin, kropotkin.passages()[0])
    prompt = PromptBuilder().build_tradition_comparison_prompt(
        "the state", [("Marxism", [own], []), ("Syndicalism", [], [other])]
    )

    assert "## Marxism\n\n### In its own words\n\n[1]" in prompt.user
    assert "## Syndicalism\n\n### Described by others\n\n[2]" in prompt.user
    with pytest.raises(ValueError):
        PromptBuilder().build_tradition_comparison_prompt("the state", [("Marxism", [], [])])


def test_tradition_prompt_lists_each_author_with_titles():
    prompt = PromptBuilder().build_tradition_prompt(
        "the state", [("Peter Kropotkin", ["The Conquest of Bread"]), ("Karl Marx", ["Capital", "Grundrisse"])]
    )

    assert "- Peter Kropotkin: The Conquest of Bread" in prompt.user
    assert "- Karl Marx: Capital; Grundrisse" in prompt.user
    assert 'named "Marxism"' in prompt.system


def test_a_disagreement_headed_with_its_sides_is_split_at_the_bar():
    # A live run headed disagreements "Leninism vs Anarchism | ...", which
    # the format does not give them, so the bar was printed.
    parsed = parse_tradition_comparison(
        "disagreement: Leninism vs Anarchism | A dictatorship of the proletariat [4, 10].\n"
        "disagreement: Whether the state can serve the revolution [1, 3]."
    )

    assert [(d.sides, d.text) for d in parsed.disagreements] == [
        ("Leninism vs Anarchism", "A dictatorship of the proletariat."),
        ("", "Whether the state can serve the revolution."),
    ]


def test_prompts_keep_leninism_within_marxism_and_editors_out_of_own_words():
    # A live run listed Leninism apart from Marxism, so the platform's
    # "Marxist assessment" criticised Leninism; and it took an editor's
    # introduction to Luxemburg as her own words.
    builder = PromptBuilder()
    assert "do not list Leninism as another tradition" in builder.build_tradition_prompt("x", []).system
    corpus = ResearchCorpus()
    book = Book(title="T", author="A", text="Text.")
    source = corpus.add_passage(book, book.passages()[0])
    system = builder.build_tradition_comparison_prompt("x", [("Marxism", [source], [])]).system
    assert "editor's introduction" in system
