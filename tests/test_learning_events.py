from datetime import datetime

import pytest

from praxis.documents import Book
from praxis.persistence import Database, SQLReaderProfileRepository
from praxis.reader_model import AssessmentSource, KnowledgeLevel
from praxis.reader_model.events import (
    ActivityObserver,
    DocumentRead,
    LearningEventBus,
    PrerequisiteMarkedKnown,
    TopicResearched,
)
from praxis.reader_model.service import ReaderProfileService
from praxis.reader_model.updater import ReaderModelUpdater


class Recorder(ActivityObserver):
    def __init__(self, log, name, fail=False):
        self.log, self.name, self.fail = log, name, fail

    def on_activity(self, activity):
        self.log.append((self.name, activity))
        if self.fail:
            raise RuntimeError("observer bug")


# --- LearningEventBus -------------------------------------------------------


def test_observers_are_notified_in_subscription_order():
    log, bus = [], LearningEventBus()
    bus.subscribe(Recorder(log, "a"))
    bus.subscribe(Recorder(log, "b"))

    bus.publish(TopicResearched("state"))

    assert [name for name, _ in log] == ["a", "b"]


def test_subscribing_twice_notifies_once_and_unsubscribe_stops_notifications():
    log, bus = [], LearningEventBus()
    observer = Recorder(log, "a")
    bus.subscribe(observer)
    bus.subscribe(observer)
    bus.publish(TopicResearched("x"))
    bus.unsubscribe(observer)
    bus.publish(TopicResearched("y"))

    assert len(log) == 1


def test_failing_observer_does_not_stop_the_others():
    log, bus = [], LearningEventBus()
    bus.subscribe(Recorder(log, "broken", fail=True))
    bus.subscribe(Recorder(log, "ok"))

    bus.publish(TopicResearched("x"))

    assert [name for name, _ in log] == ["broken", "ok"]


# --- ReaderModelUpdater -----------------------------------------------------


@pytest.fixture
def setup():
    database = Database()
    profiles = ReaderProfileService(
        SQLReaderProfileRepository(database), clock=lambda: datetime(2026, 11, 18)
    )
    bus = LearningEventBus()
    bus.subscribe(ReaderModelUpdater(profiles))
    yield bus, profiles
    database.close()


def book(title="Manifesto", topics=("class struggle", "capitalism")):
    return Book(title=title, author="Marx", text="1.\n\n2.\n\n3.\n\n4.", topics=topics)


def test_opening_a_text_records_progress_and_interest_once(setup):
    bus, profiles = setup
    text = book()

    bus.publish(DocumentRead(text, 1))
    bus.publish(DocumentRead(text, 2))

    profile = profiles.get_profile()
    assert profile.history.get(text.id).furthest_paragraph == 2
    assert profile.interests.weights == {"class struggle": 0.5, "capitalism": 0.5}
    assert profile.knowledge.areas == {}


def test_finishing_a_text_infers_introductory_knowledge_once(setup):
    bus, profiles = setup
    text = book()

    bus.publish(DocumentRead(text, 4))
    bus.publish(DocumentRead(text, 4))

    area = profiles.get_profile().knowledge.areas["capitalism"]
    assert (area.level, area.source, area.evidence) == (
        KnowledgeLevel.INTRODUCTORY,
        AssessmentSource.INFERRED,
        1,
    )


def test_second_finished_text_on_a_topic_infers_intermediate(setup):
    bus, profiles = setup

    bus.publish(DocumentRead(book("A", ("state",)), 4))
    bus.publish(DocumentRead(book("B", ("state",)), 4))

    assert profiles.get_profile().knowledge.get_level("state") is KnowledgeLevel.INTERMEDIATE


def test_research_adds_interest(setup):
    bus, profiles = setup

    bus.publish(TopicResearched("Imperialism"))

    assert profiles.get_profile().interests.top() == ["imperialism"]


def test_marking_a_prerequisite_known_is_a_stated_assessment(setup):
    bus, profiles = setup

    bus.publish(PrerequisiteMarkedKnown("commodity"))

    area = profiles.get_profile().knowledge.areas["commodity"]
    assert area.source is AssessmentSource.USER_STATED
    assert area.level is KnowledgeLevel.INTRODUCTORY


def test_marking_known_does_not_lower_a_higher_level(setup):
    bus, profiles = setup
    profiles.correct_knowledge_assessment("commodity", KnowledgeLevel.ADVANCED)

    bus.publish(PrerequisiteMarkedKnown("commodity"))

    assert profiles.get_profile().knowledge.get_level("commodity") is KnowledgeLevel.ADVANCED


class CountingRepository(SQLReaderProfileRepository):
    def __init__(self, database):
        super().__init__(database)
        self.loads = self.saves = 0

    def load(self):
        self.loads += 1
        return super().load()

    def save(self, profile):
        self.saves += 1
        super().save(profile)


@pytest.mark.parametrize(
    "activity",
    [
        DocumentRead(book(), 4),  # finishing: history, interests and knowledge all change
        TopicResearched("state"),
        PrerequisiteMarkedKnown("commodity"),
    ],
)
def test_each_activity_loads_and_saves_the_profile_once(activity):
    database = Database()
    repository = CountingRepository(database)
    bus = LearningEventBus()
    bus.subscribe(ReaderModelUpdater(ReaderProfileService(repository)))

    bus.publish(activity)

    assert (repository.loads, repository.saves) == (1, 1)
    database.close()


def test_reading_record_uses_document_length(setup):
    bus, profiles = setup
    text = book()

    bus.publish(DocumentRead(text, 2))

    record = profiles.get_profile().history.get(text.id)
    assert (record.furthest_paragraph, record.total_paragraphs) == (2, 4)
