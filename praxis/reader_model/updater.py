"""Concrete observer that turns learning activity into reader-model updates."""

from __future__ import annotations

from praxis.reader_model.events import (
    ActivityObserver,
    DocumentRead,
    LearningActivity,
    PrerequisiteMarkedKnown,
    TopicResearched,
)
from praxis.reader_model.models import AssessmentSource, KnowledgeLevel, ReaderProfile
from praxis.reader_model.service import ReaderProfileService

# Interest added to each of a text's topics the first time it is opened.
OPENED_TEXT_INTEREST = 0.5
RESEARCH_INTEREST = 1.0


class ReaderModelUpdater(ActivityObserver):
    """Each activity becomes exactly one profile update: one load, every
    change applied in memory, one save."""

    def __init__(self, profiles: ReaderProfileService) -> None:
        self._profiles = profiles

    def on_activity(self, activity: LearningActivity) -> None:
        if isinstance(activity, DocumentRead):
            self._document_read(activity)
        elif isinstance(activity, TopicResearched):
            self._profiles.update_profile(
                lambda profile: profile.interests.add(activity.topic, RESEARCH_INTEREST)
            )
        elif isinstance(activity, PrerequisiteMarkedKnown):
            self._profiles.update_profile(
                lambda profile: _mark_known(profile, activity.topic)
            )

    def _document_read(self, activity: DocumentRead) -> None:
        document = activity.document
        total = len(document.passages())
        now = self._profiles.now()

        def change(profile: ReaderProfile) -> None:
            before = profile.history.get(document.id)
            record = profile.history.record(
                document.id, document.title, activity.paragraph, total, now
            )
            if before is None:
                for topic in document.topics:
                    profile.interests.add(topic, OPENED_TEXT_INTEREST)

            if record.completed and not (before and before.completed):
                for topic in document.topics:
                    # One finished text suggests an introduction; a second on
                    # the same topic suggests more. Reading alone never
                    # implies ADVANCED.
                    level = (
                        KnowledgeLevel.INTERMEDIATE
                        if profile.knowledge.get_level(topic) >= KnowledgeLevel.INTRODUCTORY
                        else KnowledgeLevel.INTRODUCTORY
                    )
                    profile.knowledge.update_level(topic, level)

        self._profiles.update_profile(change)


def _mark_known(profile: ReaderProfile, topic: str) -> None:
    """The reader's own statement, not an inference. It only says "at least
    introductory", so a higher level is left alone."""
    if profile.knowledge.get_level(topic) < KnowledgeLevel.INTRODUCTORY:
        profile.knowledge.update_level(
            topic, KnowledgeLevel.INTRODUCTORY, AssessmentSource.USER_STATED
        )
