"""Application access to the reader model.

Every change goes through load → change → save, so callers never hold a
stale copy of the profile across operations.

Imported as ``praxis.reader_model.service`` (not re-exported by the package)
because persistence depends on the model classes and this module depends on
persistence.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from praxis.documents import Document
from praxis.persistence import ReaderProfileRepository
from praxis.reader_model.models import (
    AssessmentSource,
    ExplanationDepth,
    KnowledgeLevel,
    ReaderProfile,
    ReadingRecord,
)

Clock = Callable[[], datetime]


class ReaderProfileService:
    def __init__(
        self, repository: ReaderProfileRepository, clock: Clock = datetime.now
    ) -> None:
        self._repository = repository
        self._clock = clock

    def get_profile(self) -> ReaderProfile:
        return self._repository.load()

    def update_profile(self, change: Callable[[ReaderProfile], object]) -> ReaderProfile:
        """Apply ``change`` to the stored profile and save the result."""
        profile = self._repository.load()
        change(profile)
        self._repository.save(profile)
        return profile

    # --- corrections made by the reader (F13) ------------------------------

    def correct_knowledge_assessment(self, topic: str, level: KnowledgeLevel) -> ReaderProfile:
        return self.update_profile(
            lambda p: p.knowledge.update_level(topic, level, AssessmentSource.USER_STATED)
        )

    def remove_knowledge_assessment(self, topic: str) -> bool:
        removed = []
        self.update_profile(lambda p: removed.append(p.knowledge.remove(topic)))
        return removed[0]

    def add_interest(self, topic: str) -> ReaderProfile:
        return self.update_profile(lambda p: p.interests.add(topic, stated=True))

    def remove_interest(self, topic: str) -> bool:
        removed = []
        self.update_profile(lambda p: removed.append(p.interests.remove(topic)))
        return removed[0]

    def set_explanation_depth(self, depth: ExplanationDepth) -> ReaderProfile:
        return self.update_profile(lambda p: setattr(p, "explanation_depth", depth))

    def set_personalization(self, enabled: bool) -> ReaderProfile:
        return self.update_profile(lambda p: setattr(p, "personalization_enabled", enabled))

    def set_background(self, background: str) -> ReaderProfile:
        return self.update_profile(lambda p: setattr(p, "background", background.strip()))

    def reset(self) -> ReaderProfile:
        """Forget everything known about the reader."""
        profile = ReaderProfile()
        self._repository.save(profile)
        return profile

    # --- observations from activity (used by ReaderModelUpdater) ----------

    def record_reading(self, document: Document, paragraph: int) -> ReadingRecord:
        total = len(document.passages())
        records = []
        self.update_profile(
            lambda p: records.append(
                p.history.record(document.id, document.title, paragraph, total, self._clock())
            )
        )
        return records[0]

    def infer_knowledge(self, topic: str, level: KnowledgeLevel) -> bool:
        changed = []
        self.update_profile(lambda p: changed.append(p.knowledge.update_level(topic, level)))
        return changed[0]

    def infer_interest(self, topic: str, weight: float = 1.0) -> None:
        self.update_profile(lambda p: p.interests.add(topic, weight))
