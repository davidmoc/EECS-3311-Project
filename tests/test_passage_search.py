import sqlite3

import pytest

from praxis.documents import Book
from praxis.persistence import Database, SQLDocumentRepository

WAGES = (
    "The average price of wage labour is the minimum wage, the quantum of "
    "the means of subsistence which is absolutely requisite to keep the "
    "labourer in bare existence as a labourer."
)
STATE = (
    "The executive of the modern state is but a committee for managing the "
    "common affairs of the whole bourgeoisie, as the history of every state "
    "shows."
)
CLASSES = (
    "Society as a whole is more and more splitting up into two great hostile "
    "camps, into two great classes directly facing each other."
)


def manifesto():
    return Book(
        title="The Communist Manifesto",
        author="Karl Marx and Friedrich Engels",
        text="\n\n".join(["MANIFESTO OF THE COMMUNIST PARTY", WAGES, STATE, CLASSES]),
        license="Public Domain",
    )


@pytest.fixture
def repository():
    database = Database()
    yield SQLDocumentRepository(database)
    database.close()


def test_finds_the_passage_that_discusses_the_question(repository):
    document = manifesto()
    repository.save(document)

    matches = repository.search_passages("What is the minimum wage?")

    assert [m.passage.text for m in matches] == [WAGES]
    assert matches[0].passage.locator == "¶2"
    assert matches[0].passage.id == document.passages()[1].id


def test_common_words_do_not_count_as_matches(repository):
    repository.save(manifesto())

    # every word here is a stopword, so nothing is searched for
    assert repository.search_passages("what is the") == []


def test_stemming_matches_other_forms_of_a_word(repository):
    repository.save(manifesto())

    matches = repository.search_passages("class")

    assert [m.passage.text for m in matches] == [CLASSES]


def test_best_match_comes_first(repository):
    repository.save(manifesto())

    matches = repository.search_passages("state bourgeoisie wage")

    assert matches[0].passage.text == STATE
    assert matches[0].score > matches[1].score


def test_limit_caps_the_number_of_matches(repository):
    repository.save(manifesto())

    assert len(repository.search_passages("state wage class", limit=2)) == 2
    assert repository.search_passages("state", limit=0) == []


def test_headings_are_not_indexed_as_evidence(repository):
    repository.save(manifesto())

    assert repository.search_passages("manifesto communist party") == []


def test_match_carries_metadata_but_not_the_whole_text(repository):
    repository.save(manifesto())

    document = repository.search_passages("wage")[0].document

    assert document.title == "The Communist Manifesto"
    assert document.author == "Karl Marx and Friedrich Engels"
    assert document.can_reproduce()
    assert document.text == ""


@pytest.mark.parametrize(
    "query", ['"unbalanced', "state AND", "NEAR(state)", "wage*", "state)", "-state"]
)
def test_search_syntax_typed_by_the_user_is_treated_as_words(repository, query):
    repository.save(manifesto())

    repository.search_passages(query)  # must not raise an FTS syntax error


def test_saving_again_replaces_the_indexed_passages(repository):
    document = manifesto()
    repository.save(document)
    document.text = CLASSES
    repository.save(document)

    assert repository.search_passages("wage") == []
    assert len(repository.search_passages("classes")) == 1


def test_documents_stored_before_the_index_existed_are_indexed(tmp_path):
    path = tmp_path / "praxis.db"
    database = Database(path)
    SQLDocumentRepository(database).save(manifesto())
    database.connection.execute("DELETE FROM passage_index")
    database.connection.execute("DELETE FROM indexed_documents")
    database.connection.commit()
    database.close()

    database = Database(path)
    matches = SQLDocumentRepository(database).search_passages("wage")
    database.close()

    assert [m.passage.text for m in matches] == [WAGES]


def test_index_and_document_are_saved_together(repository, monkeypatch):
    document = manifesto()

    def broken_index(_document):
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(repository, "_index_passages", broken_index)
    with pytest.raises(sqlite3.OperationalError):
        repository.save(document)

    assert repository.find_by_id(document.id) is None


def test_opening_an_indexed_database_does_not_read_the_passage_index(tmp_path):
    path = tmp_path / "praxis.db"
    database = Database(path)
    SQLDocumentRepository(database).save(manifesto())
    database.close()

    database = Database(path)
    statements = []
    database.connection.set_trace_callback(statements.append)
    SQLDocumentRepository(database)
    database.close()

    assert statements, "the check should still run"
    assert not [s for s in statements if "passage_index" in s]


def test_document_with_no_indexable_passages_is_not_reindexed_on_open(tmp_path):
    path = tmp_path / "praxis.db"
    database = Database(path)
    SQLDocumentRepository(database).save(Book(title="Title page only", author="A", text="CHAPTER I"))
    statements = []
    database.connection.set_trace_callback(statements.append)
    SQLDocumentRepository(database)
    database.close()

    assert not [s for s in statements if "INSERT" in s or "DELETE" in s]
