import pytest

from praxis.documents import Book
from praxis.library import (
    ProviderError,
    PublicTextArchiveAdapter,
    SourceReference,
    clean_text,
    directory_fetcher,
)

RAW_BOOK = "﻿" + "\r\n".join(
    [
        "The Project Gutenberg eBook of The Communist Manifesto",
        "",
        "Title: The Communist Manifesto",
        "",
        "Author: Karl Marx and Friedrich Engels",
        "",
        "*** START OF THE PROJECT GUTENBERG EBOOK THE COMMUNIST MANIFESTO ***",
        "",
        "A spectre is haunting Europe--the spectre",
        "of Communism.",
        "",
        "",
        "The history of all hitherto existing society",
        "is the history of class struggles.",
        "*** END OF THE PROJECT GUTENBERG EBOOK THE COMMUNIST MANIFESTO ***",
        "",
        "Licence text that must not appear in the library.",
    ]
)


class FakeFetcher:
    def __init__(self, text=RAW_BOOK, error=None):
        self.text, self.error, self.urls = text, error, []

    def __call__(self, url):
        self.urls.append(url)
        if self.error:
            raise self.error
        return self.text


def test_clean_text_drops_licence_and_joins_wrapped_lines():
    assert clean_text(RAW_BOOK) == (
        "A spectre is haunting Europe--the spectre of Communism.\n\n"
        "The history of all hitherto existing society is the history of "
        "class struggles."
    )


def test_cleaned_text_splits_into_one_passage_per_paragraph():
    book = Book(title="Manifesto", author="Marx", text=clean_text(RAW_BOOK))

    passages = book.passages()

    assert [p.locator for p in passages] == ["¶1", "¶2"]
    assert passages[1].text.startswith("The history of all")


def test_clean_text_drops_old_style_footer_line():
    raw = "*** START OF THIS PROJECT GUTENBERG EBOOK X ***\nBody.\n\nEnd of Project Gutenberg's X, by Y\n\nmore licence"

    assert clean_text(raw) == "Body."


def test_start_marker_wrapped_onto_two_lines_is_fully_removed():
    raw = "*** START OF THIS PROJECT GUTENBERG EBOOK REVOLUTION AND\nCOUNTER-REVOLUTION***\n\nBody."

    assert clean_text(raw) == "Body."


def test_clean_text_without_markers_keeps_everything():
    assert clean_text("one\ntwo\n\nthree") == "one two\n\nthree"


@pytest.mark.parametrize(
    ("source_id", "path"),
    [
        ("61", "/6/61/61-0.txt"),
        ("1346", "/1/3/4/1346/1346-0.txt"),
        ("7", "/0/7/7-0.txt"),
    ],
)
def test_mirror_url_layout(source_id, path):
    adapter = PublicTextArchiveAdapter(base_url="https://mirror.test/")

    assert adapter.url_for(source_id) == "https://mirror.test" + path


def test_non_numeric_id_is_rejected_before_any_download():
    fetcher = FakeFetcher()
    adapter = PublicTextArchiveAdapter(fetcher=fetcher)

    with pytest.raises(ProviderError):
        adapter.fetch(SourceReference("../etc/passwd"))
    assert fetcher.urls == []


def test_fetch_builds_a_reproducible_book_from_header_metadata():
    adapter = PublicTextArchiveAdapter(fetcher=FakeFetcher())

    book = adapter.fetch(SourceReference("61", topics=("class struggle",)))

    assert isinstance(book, Book)
    assert book.title == "The Communist Manifesto"
    assert book.author == "Karl Marx and Friedrich Engels"
    assert book.topics == ("class struggle",)
    assert book.source_url == "https://www.gutenberg.org/ebooks/61"
    assert book.can_reproduce() and book.downloadable
    assert "Licence text" not in book.text


def test_reference_metadata_overrides_the_header():
    adapter = PublicTextArchiveAdapter(fetcher=FakeFetcher())

    book = adapter.fetch(SourceReference("61", title="Manifesto", author="Marx"))

    assert (book.title, book.author) == ("Manifesto", "Marx")


def test_download_failure_surfaces_as_provider_error():
    adapter = PublicTextArchiveAdapter(fetcher=FakeFetcher(error=ProviderError("down")))

    with pytest.raises(ProviderError):
        adapter.fetch(SourceReference("61"))


def test_book_without_any_title_is_rejected():
    adapter = PublicTextArchiveAdapter(fetcher=FakeFetcher(text="no header at all"))

    with pytest.raises(ProviderError):
        adapter.fetch(SourceReference("99"))


def test_importing_the_same_book_twice_gives_the_same_id():
    adapter = PublicTextArchiveAdapter(fetcher=FakeFetcher())

    assert adapter.fetch(SourceReference("61")).id == adapter.fetch(SourceReference("61")).id
    assert adapter.fetch(SourceReference("61")).id != adapter.fetch(SourceReference("62")).id


def test_directory_fetcher_reads_local_copies(tmp_path):
    (tmp_path / "61.txt").write_text(RAW_BOOK, encoding="utf-8")
    adapter = PublicTextArchiveAdapter(fetcher=directory_fetcher(tmp_path))

    assert adapter.fetch(SourceReference("61")).title == "The Communist Manifesto"
    with pytest.raises(ProviderError):
        adapter.fetch(SourceReference("1346"))


@pytest.mark.parametrize(
    "credit",
    [
        "Produced by Odessa Paige Turner and the\nOnline Distributed Proofreading Team",
        "E-text prepared by Odessa Paige Turner and the Project Gutenberg Online",
        "Note: Images of the original pages are available through the Google Books Library Project.",
        # As they open Gutenberg books 46423 and 41405.
        "  ------------------------------------------------\n  Transcriber’s Note:\n  +Bold text+ is enclosed within plus signs.",
        "  [Transcriber's notes:\n  Inconsistent hyphenation and use of umlauts retained.]",
        "+----------------------+\n|Transcriber's note: |\n| Italics are _thus_. |",  # 27814
    ],
)
def test_volunteer_credits_at_the_start_are_dropped(credit):
    raw = f"*** START OF THE PROJECT GUTENBERG EBOOK X ***\n\n{credit}\n\nThe author's first words."

    assert clean_text(raw) == "The author's first words."


def test_credit_wording_later_in_the_book_is_kept():
    body = "\n\n".join(f"Paragraph {n}." for n in range(1, 7))
    raw = f"{body}\n\nProduced by the embroidery of lace."

    assert clean_text(raw).endswith("Produced by the embroidery of lace.")


def test_a_transcribers_note_closing_the_book_is_dropped():
    # Book 41405 ends with "[Transcriber's notes: List of errors: ...".
    body = "\n\n".join(f"Paragraph {n}." for n in range(1, 9))
    raw = f"{body}\n\n[Transcriber's notes: List of errors: Page 20 \"stook\" changed to \"stock\"]"

    assert clean_text(raw).endswith("Paragraph 8.")


def test_the_phrase_transcribers_note_mid_book_is_kept():
    body = "\n\n".join(f"Paragraph {n}." for n in range(1, 8))
    middle = "Transcriber's notes were how monks kept accounts, the author says."
    raw = f"{body}\n\n{middle}\n\n{body}"

    assert middle in clean_text(raw)


def test_a_closing_box_of_corrected_misprints_is_dropped():
    # Book 31933 ends with a boxed list of typographical corrections.
    body = "\n\n".join(f"Paragraph {n}." for n in range(1, 9))
    box = "+-----+\n| Typographical errors corrected in the text: |\n| Page 40: socalled replaced with so-called |"

    assert clean_text(f"{body}\n\n{box}").endswith("Paragraph 8.")
