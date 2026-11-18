"""Concrete observer that turns learning activity into reader-model updates."""

from __future__ import annotations

from praxis.reader_model.events import (
    ActivityObserver,
    DocumentRead,
    LearningActivity,
    PrerequisiteMarkedKnown,
    TopicResearched,
)
from praxis.reader_model.models import KnowledgeLevel
from praxis.reader_model.service import ReaderProfileService

# Interest added to each of a text's topics the first time it is opened.
OPENED_TEXT_INTEREST = 0.5
RESEARCH_INTEREST = 1.0


class ReaderModelUpdater(ActivityObserver):
    def __init__(self, profiles: ReaderProfileService) -> None:
        self._profiles = profiles

    def on_activity(self, activity: LearningActivity) -> None:
        if isinstance(activity, DocumentRead):
            self._document_read(activity)
        elif isinstance(activity, TopicResearched):
            self._profiles.infer_interest(activity.topic, RESEARCH_INTEREST)
        elif isinstance(activity, PrerequisiteMarkedKnown):
            # The reader's own statement, not an inference. It only says
            # "at least introductory", so a higher level is left alone.
            knowledge = self._profiles.get_profile().knowledge
            if knowledge.get_level(activity.topic) < KnowledgeLevel.INTRODUCTORY:
                self._profiles.correct_knowledge_assessment(
                    activity.topic, KnowledgeLevel.INTRODUCTORY
                )

    def _document_read(self, activity: DocumentRead) -> None:
        document = activity.document
        before = self._profiles.get_profile().history.get(document.id)
        record = self._profiles.record_reading(document, activity.paragraph)

        if before is None:
            for topic in document.topics:
                self._profiles.infer_interest(topic, OPENED_TEXT_INTEREST)

        just_completed = record.completed and not (before and before.completed)
        if just_completed:
            knowledge = self._profiles.get_profile().knowledge
            for topic in document.topics:
                # One finished text suggests an introduction; a second on the
                # same topic suggests more. Reading alone never implies ADVANCED.
                level = (
                    KnowledgeLevel.INTERMEDIATE
                    if knowledge.get_level(topic) >= KnowledgeLevel.INTRODUCTORY
                    else KnowledgeLevel.INTRODUCTORY
                )
                self._profiles.infer_knowledge(topic, level)
