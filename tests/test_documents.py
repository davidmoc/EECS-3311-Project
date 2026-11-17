import pytest

from praxis.documents import Article, Book, Document, NewsArticle
from praxis.documents.models import EXCERPT_LIMIT

TEXT = """The history of all hitherto existing society is the history of class struggles.

Freeman and slave, patrician and plebeian, lord and serf.


The modern bourgeois society has not done away with class antagonisms."""


def make_book(**overrides):
    fields = dict(
        title="Manifesto of the Communist Party",
        author="Marx and Engels",
        text=TEXT,
        license="Public Domain",
    )
    fields.update(overrides)
    return Book(**fields)


def test_blank_title_is_rejected():
    with pytest.raises(ValueError):
        Document(title="   ", author="Nobody")


def test_passages_split_on_blank_lines_and_number_from_one():
    passages = make_book().passages()

    assert [p.locator for p in passages] == ["¶1", "¶2", "¶3"]
    assert passages[1].text == "Freeman and slave, patrician and plebeian, lord and serf."


def test_document_without_text_has_no_passages():
    assert make_book(text="  \n\n ").passages() == []


def test_passage_ids_are_stable_across_calls_but_unique_per_document():
    book = make_book()
    other = make_book()

    assert [p.id for p in book.passages()] == [p.id for p in book.passages()]
    assert book.passages()[0].id != other.passages()[0].id


def test_find_passages_requires_every_term_and_ignores_case():
    book = make_book()

    assert [p.locator for p in book.find_passages("CLASS")] == ["¶1", "¶3"]
    assert [p.locator for p in book.find_passages("class bourgeois")] == ["¶3"]
    assert book.find_passages("feudalism") == []
    assert book.find_passages("   ") == []


@pytest.mark.parametrize(
    "license_text, expected",
    [
        ("Public Domain", True),
        ("public domain (author died 1883)", True),
        ("CC BY-SA 4.0", True),
        ("All rights reserved", False),
        ("", False),
    ],
)
def test_reproduction_depends_on_license(license_text, expected):
    assert make_book(license=license_text).can_reproduce() is expected


def test_citation_points_back_to_the_passage():
    book = make_book()
    passage = book.passages()[0]

    citation = book.cite(passage)

    assert citation.document_id == book.id
    assert citation.quoted_text == passage.text
    assert citation.format() == (
        "Marx and Engels, “Manifesto of the Communist Party”, ¶1"
    )


def test_restricted_text_is_only_excerpted():
    long_paragraph = "word " * 200
    article = Article(
        title="Recent essay",
        author="A. Writer",
        text=long_paragraph,
        license="All rights reserved",
    )

    quoted = article.cite(article.passages()[0]).quoted_text

    assert quoted.endswith("…")
    assert len(quoted) <= EXCERPT_LIMIT + 1


def test_citing_a_passage_from_another_document_is_rejected():
    book, other = make_book(), make_book()

    with pytest.raises(ValueError):
        book.cite(other.passages()[0])


def test_document_kinds_identify_subclasses():
    assert Document(title="t", author="a").kind == "document"
    assert Book(title="t", author="a").kind == "book"
    assert Article(title="t", author="a").kind == "article"
    news = NewsArticle(title="t", author="a", outlet="Wire Service")
    assert (news.kind, news.outlet) == ("news", "Wire Service")
    assert isinstance(news, Article)
