"""The reader's personal workspace (F15): things saved to come back to."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4


class SavedItemKind(Enum):
    DOCUMENT = "document"
    PASSAGE = "passage"
    ANNOTATION = "annotation"
    EVENT = "event"
    RESEARCH = "research"
    COMPARISON = "comparison"
    NOTE = "note"


@dataclass
class SavedItem:
    """A saved reference plus a snapshot of its content.

    ``reference`` identifies the original (a document id, passage id, ...).
    ``content`` keeps a copy of what was saved, so the item stays useful if
    the original source later becomes unavailable.
    """

    kind: SavedItemKind
    title: str
    reference: str = ""
    content: str = ""
    note: str = ""
    tags: tuple[str, ...] = ()
    saved_at: datetime = field(default_factory=datetime.now)
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("A saved item needs a title.")
        self.tags = tuple(sorted({t.strip().lower() for t in self.tags if t.strip()}))

    def matches(self, query: str) -> bool:
        """Whether every word of ``query`` appears somewhere in the item."""
        haystack = " ".join((self.title, self.content, self.note, " ".join(self.tags))).lower()
        terms = query.lower().split()
        return bool(terms) and all(term in haystack for term in terms)


@dataclass
class Workspace:
    items: list[SavedItem] = field(default_factory=list)

    def add(self, item: SavedItem) -> SavedItem:
        """Add ``item``. Saving the same original twice updates the existing
        entry (its note and tags) instead of creating a duplicate."""
        existing = self.find_reference(item.kind, item.reference) if item.reference else None
        if existing is None:
            self.items.append(item)
            return item
        if item.note:
            existing.note = item.note
        existing.tags = tuple(sorted(set(existing.tags) | set(item.tags)))
        existing.content = item.content or existing.content
        return existing

    def remove(self, item_id: UUID) -> SavedItem | None:
        for index, item in enumerate(self.items):
            if item.id == item_id:
                return self.items.pop(index)
        return None

    def find_reference(self, kind: SavedItemKind, reference: str) -> SavedItem | None:
        return next(
            (i for i in self.items if i.kind is kind and i.reference == reference), None
        )

    def search(self, query: str) -> list[SavedItem]:
        return [item for item in self.newest_first() if item.matches(query)]

    def newest_first(self, kind: SavedItemKind | None = None) -> list[SavedItem]:
        items = [i for i in self.items if kind is None or i.kind is kind]
        return sorted(items, key=lambda i: i.saved_at, reverse=True)
