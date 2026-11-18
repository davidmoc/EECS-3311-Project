"""Observer pattern: learning activity is published, interested parts react.

Controllers publish what the reader did to ``LearningEventBus`` (the
subject). Observers such as ``ReaderModelUpdater`` decide what it means.
Publishers therefore never need to know how the reader model is updated,
and new observers can be added without touching the publishers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from praxis.documents import Document

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LearningActivity:
    """Base class of everything that can be published."""


@dataclass(frozen=True)
class DocumentRead(LearningActivity):
    document: Document
    paragraph: int  # 1-based furthest paragraph the reader reached


@dataclass(frozen=True)
class TopicResearched(LearningActivity):
    topic: str


@dataclass(frozen=True)
class PrerequisiteMarkedKnown(LearningActivity):
    """The reader said they already understand a suggested prerequisite."""

    topic: str


class ActivityObserver(ABC):
    @abstractmethod
    def on_activity(self, activity: LearningActivity) -> None: ...


class LearningEventBus:
    def __init__(self) -> None:
        self._observers: list[ActivityObserver] = []

    def subscribe(self, observer: ActivityObserver) -> None:
        if observer not in self._observers:
            self._observers.append(observer)

    def unsubscribe(self, observer: ActivityObserver) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    def publish(self, activity: LearningActivity) -> None:
        """Notify every observer in subscription order.

        A failing observer is logged and skipped: updating the reader model
        is secondary to what the reader was doing, so it must never break it.
        """
        for observer in list(self._observers):
            try:
                observer.on_activity(activity)
            except Exception:
                logger.exception("Observer %r failed on %r", observer, activity)
