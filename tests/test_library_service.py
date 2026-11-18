import json
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest

from praxis.documents import Book
from praxis.library import (
    DEFAULT_CATALOGUE,
    DocumentProvider,
    LibraryError,
    LibraryService,
    ProviderError,
    PublicTextArchiveAdapter,
    SourceReference,
    directory_fetcher,
    read_catalogue,
)
from praxis.persistence import Database, SQLDocumentRepository


class FakeProvider(DocumentProvider):
    def __init__(self, unavailable=()):
        self.unavailable = set(unavailable)

    def fetch(self, reference):
        if reference.source_id in self.unavailable:
            raise ProviderError(f"{reference.source_id} unavailable")
        return Book(
            id=UUID(int=int(reference.source_id)),
            title=reference.title or f"Book {reference.source_id}",
            author=reference.author or "Author",
            text="First paragraph.\n\nSecond paragraph.",
            license="Public domain",
            downloadable=True,
            topics=reference.topics,
        )


@pytest.fixture
def repository():
    database = Database()
    yield SQLDocumentRepository(database)
    database.close()


@pytest.fixture
def library(repository):
    repository.save(
        Book(
            title="The Communist Manifesto",
            author="Marx and Engels",
            text="A spectre is haunting Europe.",
            license="Public domain",
            downloadable=True,
            topics=("Class Struggle", "communism"),
        )
    )
    repository.save(
        Book(
            title="Modern Commentary",
            author="Someone Living",
            text="Copyrighted prose.",
            license="All rights reserved",
            source_url="https://example.org/commentary",
            topics=("class struggle",),
        )
    )
    return LibraryService(repository, FakeProvider())


def test_search_delegates_to_the_repository(library):
    assert [d.title for d in library.search("spectre")] == ["The Communist Manifesto"]


def test_browse_without_topic_lists_everything(library):
    assert len(library.browse()) == 2


def test_browse_by_topic_ignores_letter_case(library):
    assert [d.title for d in library.browse("communism")] == ["The Communist Manifesto"]
    assert len(library.browse("CLASS STRUGGLE")) == 2
    assert library.browse("anarchism") == []


def test_topics_are_counted_most_common_first(library):
    assert library.topics() == [("class struggle", 2), ("communism", 1)]


def test_get_document_by_unique_prefix(library):
    manifesto = library.search("spectre")[0]

    assert library.get_document(manifesto.id) == manifesto
    assert library.get_document(str(manifesto.id)[:8]) == manifesto


@pytest.mark.parametrize("bad_id", ["", "zzzz", UUID(int=0)])
def test_unknown_id_raises_library_error(library, bad_id):
    with pytest.raises(LibraryError):
        library.get_document(bad_id)


def test_ambiguous_prefix_is_rejected(repository):
    for n in (1, 2):
        repository.save(Book(id=UUID(f"abcd000{n}-0000-0000-0000-000000000000"), title=f"T{n}", author="A"))

    with pytest.raises(LibraryError, match="matches 2"):
        LibraryService(repository).get_document("abcd")


def test_download_writes_public_domain_text_with_its_source(library, tmp_path):
    manifesto = library.search("spectre")[0]

    path = library.download(manifesto.id, tmp_path / "out")

    assert path == tmp_path / "out" / "the-communist-manifesto.txt"
    content = path.read_text(encoding="utf-8")
    assert content.startswith("The Communist Manifesto\nMarx and Engels")
    assert "Licence: Public domain" in content
    assert content.endswith("A spectre is haunting Europe.")


def test_download_of_restricted_text_is_refused_and_points_to_source(library, tmp_path):
    commentary = library.search("Modern")[0]

    with pytest.raises(LibraryError, match="example.org/commentary"):
        library.download(commentary.id, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_import_saves_the_fetched_document(repository):
    library = LibraryService(repository, FakeProvider())

    document = library.import_document(SourceReference("7", topics=("state",)))

    assert repository.find_by_id(document.id) == document
    assert library.browse("state") == [document]


def test_import_without_provider_is_an_error(repository):
    with pytest.raises(LibraryError):
        LibraryService(repository).import_document(SourceReference("7"))


def test_catalogue_import_continues_past_unavailable_texts(repository, tmp_path):
    catalogue = tmp_path / "catalogue.json"
    catalogue.write_text(
        json.dumps(
            [
                {"source_id": "1", "title": "One", "publication_date": "1848-02-21"},
                {"source_id": "2"},
                {"source_id": 3, "topics": ["state"]},
            ]
        )
    )
    library = LibraryService(repository, FakeProvider(unavailable={"2"}))

    report = library.import_catalogue(catalogue)

    assert [d.title for d in report.imported] == ["One", "Book 3"]
    assert report.failures == (("2", "2 unavailable"),)
    assert len(library.browse()) == 2


def test_read_catalogue_parses_dates_and_topics(tmp_path):
    catalogue = tmp_path / "c.json"
    catalogue.write_text('[{"source_id": "61", "publication_date": "1848-02-21", "topics": ["a"]}]')

    [reference] = read_catalogue(catalogue)

    assert reference.publication_date == date(1848, 2, 21)
    assert reference.topics == ("a",)


def test_unreadable_catalogue_is_a_library_error(tmp_path):
    with pytest.raises(LibraryError):
        read_catalogue(tmp_path / "missing.json")


def test_bundled_sample_library_imports_offline(repository):
    """The texts shipped in data/library load without network access."""
    folder = Path(DEFAULT_CATALOGUE).parent
    library = LibraryService(
        repository, PublicTextArchiveAdapter(fetcher=directory_fetcher(folder))
    )

    report = library.import_catalogue(DEFAULT_CATALOGUE)

    assert report.failures == ()
    assert len(report.imported) == len(read_catalogue(DEFAULT_CATALOGUE))
    manifesto = library.search("Communist Manifesto")[0]
    assert manifesto.publication_date == date(1848, 2, 21)
    assert manifesto.find_passages("hitherto existing societies")
