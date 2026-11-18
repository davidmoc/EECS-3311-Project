from datetime import datetime
from uuid import uuid4

import pytest

from praxis.documents import Book
from praxis.persistence import Database, SQLReaderProfileRepository
from praxis.reader_model import ExplanationDepth, KnowledgeLevel, ReaderProfile
from praxis.reader_model.service import ReaderProfileService

NOW = datetime(2026, 11, 18, 9, 30)


@pytest.fixture
def database():
    database = Database()
    yield database
    database.close()


@pytest.fixture
def service(database):
    return ReaderProfileService(SQLReaderProfileRepository(database), clock=lambda: NOW)


def manifesto():
    return Book(title="Manifesto", author="Marx", text="One.\n\nTwo.\n\nThree.")


def test_missing_profile_loads_as_empty(database):
    assert SQLReaderProfileRepository(database).load() == ReaderProfile()


def test_full_profile_round_trips_through_the_database(database, service):
    book = manifesto()
    service.correct_knowledge_assessment("dialectics", KnowledgeLevel.INTERMEDIATE)
    service.infer_knowledge("state", KnowledgeLevel.INTRODUCTORY)
    service.add_interest("labour")
    service.remove_interest("religion")
    service.record_reading(book, 2)
    service.set_explanation_depth(ExplanationDepth.DETAILED)
    service.set_personalization(False)
    service.set_background("  Engineering student.  ")

    loaded = SQLReaderProfileRepository(database).load()

    assert loaded == service.get_profile()
    assert loaded.knowledge.get_level("dialectics") is KnowledgeLevel.INTERMEDIATE
    assert loaded.interests.dismissed == {"religion"}
    assert loaded.history.get(book.id).furthest_paragraph == 2
    assert loaded.history.get(book.id).last_read == NOW
    assert loaded.explanation_depth is ExplanationDepth.DETAILED
    assert loaded.personalization_enabled is False
    assert loaded.background == "Engineering student."


def test_reader_correction_survives_later_inference(service):
    service.correct_knowledge_assessment("state", KnowledgeLevel.NONE)

    assert not service.infer_knowledge("state", KnowledgeLevel.ADVANCED)
    assert service.get_profile().knowledge.get_level("state") is KnowledgeLevel.NONE


def test_remove_reports_whether_anything_was_removed(service):
    service.infer_knowledge("state", KnowledgeLevel.INTRODUCTORY)

    assert service.remove_knowledge_assessment("state") is True
    assert service.remove_knowledge_assessment("state") is False
    assert service.remove_interest("unknown") is False


def test_record_reading_uses_document_length(service):
    record = service.record_reading(manifesto(), 3)

    assert record.total_paragraphs == 3 and record.completed


def test_reset_forgets_everything(service):
    service.add_interest("labour")

    service.reset()

    assert service.get_profile().is_sparse
