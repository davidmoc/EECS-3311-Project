"""Stored learning paths and progress (F08, UC08 steps 7-8)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from conftest import ScriptedLLM

from praxis.documents import Citation
from praxis.persistence import Database, SQLDocumentRepository
from praxis.persistence.learning_paths import SQLLearningPathRepository
from praxis.reader_model import AssessmentSource, KnowledgeLevel, ReaderProfile
from praxis.reading.prerequisites import (
    LearningPath,
    LearningStep,
    Prerequisite,
    PrerequisiteError,
    PrerequisiteService,
    StepStatus,
)
from praxis.tools import PassageSearchTool, ToolManager


def sample_path():
    reading = Citation(uuid4(), "The Communist Manifesto", "Marx and Engels", "¶1", "The history of all ...")
    return LearningPath(
        "the Brumaire",
        [
            LearningStep(Prerequisite("Class struggle", "concept", True, "class", "why", "orientation"),
                         (reading,), required=True),
            LearningStep(Prerequisite("Physiocrats", "theory", False), note="You may already know this."),
        ],
        already_known=("value",),
        personalized=True,
        target_document_id=uuid4(),
        warnings=("a warning",),
        tokens_used=42,
    )


@pytest.fixture
def database():
    database = Database()
    yield database
    database.close()


def test_a_path_survives_storage_whole(database):
    repository = SQLLearningPathRepository(database)
    path = sample_path()
    path.steps[1].status = StepStatus.SKIPPED

    repository.save(path)

    assert repository.get(path.id) == path


def test_unknown_path_is_none(database):
    assert SQLLearningPathRepository(database).get(uuid4()) is None


def test_listing_shows_progress_most_recently_changed_first(database):
    times = iter(datetime(2026, 11, 22, tzinfo=timezone.utc) + timedelta(minutes=n) for n in range(10))
    repository = SQLLearningPathRepository(database, clock=lambda: next(times))
    older, newer = sample_path(), sample_path()
    repository.save(older)
    repository.save(newer)
    older.steps[0].status = StepStatus.DONE
    repository.save(older)  # changed last, so listed first

    summaries = repository.list_recent()

    assert [s.id for s in summaries] == [older.id, newer.id]
    assert (summaries[0].step_count, summaries[0].settled_count) == (2, 1)
    assert summaries[0].target == "the Brumaire"


def test_ids_are_found_by_prefix(database):
    repository = SQLLearningPathRepository(database)
    path = sample_path()
    repository.save(path)

    assert repository.find_ids(str(path.id)[:8]) == [path.id]
    assert repository.find_ids("%") == []


# --- through the service -------------------------------------------------------


def service_with_store(database, *replies):
    tools = ToolManager()
    tools.register_tool(PassageSearchTool(SQLDocumentRepository(database)))
    return PrerequisiteService(tools, ScriptedLLM(*replies), repository=SQLLearningPathRepository(database))


REPLY = "prerequisite: Class struggle | concept | essential\nprerequisite: Physiocrats | theory | helpful"


def test_a_built_path_is_stored_and_found_again(library_database):
    service = service_with_store(library_database, REPLY)
    path = service.build_learning_path("the Brumaire")

    assert service.get_path(service.find_path(str(path.id)[:8])) == path
    assert [s.target for s in service.list_paths()] == ["the Brumaire"]


def test_a_path_with_no_steps_is_not_stored(library_database):
    profile = ReaderProfile()
    profile.knowledge.update_level("class struggle", KnowledgeLevel.INTRODUCTORY, AssessmentSource.USER_STATED)
    service = service_with_store(library_database, "prerequisite: Class struggle | concept | essential")

    assert service.build_learning_path("the Manifesto", profile).no_path_required
    assert service.list_paths() == []


def test_step_status_is_kept(library_database):
    service = service_with_store(library_database, REPLY)
    path = service.build_learning_path("the Brumaire")

    service.set_step_status(path.id, 1, StepStatus.DONE)
    service.set_step_status(path.id, 2, StepStatus.SKIPPED)

    stored = service.get_path(path.id)
    assert [s.status for s in stored.steps] == [StepStatus.DONE, StepStatus.SKIPPED]
    assert stored.settled_count == 2
    assert stored.next_step is None


def test_next_step_is_the_first_still_to_do(library_database):
    service = service_with_store(library_database, REPLY)
    path = service.build_learning_path("the Brumaire")

    number, step = service.set_step_status(path.id, 1, StepStatus.KNOWN).next_step

    assert (number, step.name) == (2, "Physiocrats")


def test_a_step_that_does_not_exist_is_refused(library_database):
    service = service_with_store(library_database, REPLY)
    path = service.build_learning_path("the Brumaire")

    with pytest.raises(PrerequisiteError, match="there is no step 3"):
        service.set_step_status(path.id, 3, StepStatus.DONE)


def test_unknown_and_ambiguous_ids_are_refused(library_database):
    service = service_with_store(library_database)
    with pytest.raises(PrerequisiteError, match="No learning path"):
        service.find_path("abc")
    with pytest.raises(PrerequisiteError, match="There is no learning path"):
        service.get_path(uuid4())


def test_without_a_store_progress_cannot_be_kept(library_database):
    tools = ToolManager()
    service = PrerequisiteService(tools, ScriptedLLM())
    with pytest.raises(PrerequisiteError, match="not being stored"):
        service.list_paths()
