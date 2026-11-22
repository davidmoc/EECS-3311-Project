"""SQLAnnotationRepository and AnnotationService's stored annotations (F06)."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from conftest import ScriptedLLM

from praxis.documents import Annotation, AnnotationType, Book
from praxis.persistence import Database, SQLAnnotationRepository, SQLDocumentRepository
from praxis.reading import AnnotationError, AnnotationService
from praxis.reading.annotations import NOT_STORED_WARNING
from praxis.tools import PassageSearchTool, ToolManager

BOOK = Book(
    title="Manifesto",
    author="Marx and Engels",
    text="\n\n".join(f"Paragraph number {n} of the text." for n in range(1, 13)),
    license="Public Domain",
)
OTHER = Book(title="Other", author="Engels", text="Some other text entirely.")


@pytest.fixture
def repository():
    database = Database()
    yield SQLAnnotationRepository(database)
    database.close()


def annotate(paragraph, content="Note.", book=BOOK, minutes=0, **fields):
    passage = book.paragraph(paragraph)
    return Annotation(
        passage_id=passage.id,
        document_id=book.id,
        locator=passage.locator,
        type=fields.pop("type", AnnotationType.ARGUMENT),
        content=content,
        created_at=datetime(2026, 11, 22, tzinfo=timezone.utc) + timedelta(minutes=minutes),
        **fields,
    )


def test_round_trip_keeps_every_field(repository):
    source = OTHER.cite(OTHER.paragraph(1))
    annotation = annotate(
        3, "The passage states [1].", type=AnnotationType.CONNECTION,
        sources=(source,), uncertainties=("one thing",), personalized=True,
    )
    repository.save(annotation)
    assert repository.for_passage(BOOK.paragraph(3).id) == [annotation]


def test_document_annotations_come_in_text_order(repository):
    # ¶10 saved first and ¶2 last: text order, not string order ("10" < "2").
    later = annotate(10, "ten", minutes=0)
    first = annotate(2, "two-b", minutes=5)
    second = annotate(2, "two-a", minutes=1)
    for annotation in (later, first, second):
        repository.save(annotation)
    repository.save(annotate(1, "other text", book=OTHER))
    assert [a.content for a in repository.for_document(BOOK.id)] == ["two-a", "two-b", "ten"]


def test_find_ids_and_delete(repository):
    annotation = annotate(1)
    repository.save(annotation)
    assert repository.find_ids(str(annotation.id)[:8]) == [annotation.id]
    assert repository.find_ids("%") == []
    assert repository.delete(annotation.id)
    assert not repository.delete(annotation.id)
    assert repository.for_passage(annotation.passage_id) == []


def test_annotation_without_document_is_not_stored(repository):
    with pytest.raises(ValueError):
        repository.save(Annotation(BOOK.paragraph(1).id, AnnotationType.ARGUMENT, "x"))


# --- through the service -------------------------------------------------------


def service_for(database, *replies, repository=None):
    tools = ToolManager()
    tools.register_tool(PassageSearchTool(SQLDocumentRepository(database)))
    return AnnotationService(
        tools, ScriptedLLM(*replies),
        repository=repository or SQLAnnotationRepository(database),
    )


def test_generated_annotation_is_stored_and_shown_again(library_database):
    book = SQLDocumentRepository(library_database).list_all()[0]
    service = service_for(library_database, "First note.", "Second note.")
    first = service.generate_annotation(book, book.paragraph(1), AnnotationType.ARGUMENT)
    service.generate_annotation(book, book.paragraph(1), AnnotationType.TERMINOLOGY)

    stored = service.get_annotations(book.paragraph(1).id)
    assert [a.content for a in stored] == ["First note.", "Second note."]
    assert stored[0] == first.annotation
    assert [a.content for a in service.annotations_for(book)] == ["First note.", "Second note."]


def test_service_finds_and_removes_by_prefix(library_database):
    book = SQLDocumentRepository(library_database).list_all()[0]
    service = service_for(library_database, "Note.")
    annotation = service.generate_annotation(
        book, book.paragraph(1), AnnotationType.ARGUMENT
    ).annotation
    found = service.find_annotation(str(annotation.id)[:8].upper())
    assert found == annotation.id
    service.remove_annotation(found)
    assert service.get_annotations(book.paragraph(1).id) == []
    with pytest.raises(AnnotationError):
        service.remove_annotation(found)
    with pytest.raises(AnnotationError, match="No annotation"):
        service.find_annotation("abcdef")


class FailingRepository(SQLAnnotationRepository):
    def save(self, annotation):
        raise sqlite3.OperationalError("database is locked")


def test_storage_failure_becomes_a_warning(library_database):
    book = SQLDocumentRepository(library_database).list_all()[0]
    service = service_for(
        library_database, "Note.", repository=FailingRepository(library_database)
    )
    result = service.generate_annotation(book, book.paragraph(1), AnnotationType.ARGUMENT)
    assert result.annotation.content == "Note."
    assert result.warnings == (NOT_STORED_WARNING.format("database is locked"),)
