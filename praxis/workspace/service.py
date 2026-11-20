"""Saving and resuming work (F15).

Imported as ``praxis.workspace.service`` for the same layering reason as the
reader-model service: persistence depends on the workspace model.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from praxis.agent import AgentResponse
from praxis.documents import Document, Passage
from praxis.persistence import WorkspaceRepository
from praxis.workspace.models import SavedItem, SavedItemKind, Workspace

Clock = Callable[[], datetime]


class WorkspaceError(ValueError):
    """A workspace request could not be completed; the message says why."""


class WorkspaceService:
    def __init__(self, repository: WorkspaceRepository, clock: Clock = datetime.now) -> None:
        self._repository = repository
        self._clock = clock

    def get_workspace(self) -> Workspace:
        return self._repository.load()

    def save_item(self, item: SavedItem) -> SavedItem:
        workspace = self._repository.load()
        saved = workspace.add(item)
        self._repository.save(workspace)
        return saved

    def save_document(self, document: Document, note: str = "", tags: tuple[str, ...] = ()) -> SavedItem:
        return self.save_item(
            SavedItem(
                kind=SavedItemKind.DOCUMENT,
                title=f"{document.title} — {document.author}",
                reference=str(document.id),
                content=document.source_url,
                note=note,
                tags=tags or document.topics,
                saved_at=self._clock(),
            )
        )

    def save_passage(
        self, document: Document, passage: Passage, note: str = "", tags: tuple[str, ...] = ()
    ) -> SavedItem:
        """Save a passage with its citation. The quoted text respects the
        document's licence, exactly as when citing it elsewhere."""
        citation = document.cite(passage)
        return self.save_item(
            SavedItem(
                kind=SavedItemKind.PASSAGE,
                title=citation.format(),
                reference=f"{document.id}#{passage.locator}",
                content=citation.quoted_text,
                note=note,
                tags=tags,
                saved_at=self._clock(),
            )
        )

    def save_answer(
        self, response: AgentResponse, note: str = "", tags: tuple[str, ...] = ()
    ) -> SavedItem:
        """Save an answer with its passages, so it can be reread without
        asking again. Saving the same question again replaces the answer."""
        question = " ".join(response.question.split())
        return self.save_item(
            SavedItem(
                kind=SavedItemKind.RESEARCH,
                title=f"Q: {question}",
                reference=f"question:{question.lower()}",
                content=render_answer(response),
                note=note,
                tags=tags,
                saved_at=self._clock(),
            )
        )

    def add_note(self, title: str, text: str = "", tags: tuple[str, ...] = ()) -> SavedItem:
        return self.save_item(
            SavedItem(SavedItemKind.NOTE, title, content=text, tags=tags, saved_at=self._clock())
        )

    def get_item(self, item_id: str) -> SavedItem:
        """Find an item by id or unambiguous id prefix."""
        prefix = item_id.strip().lower()
        if not prefix:
            raise WorkspaceError("An item id is required.")
        matches = [i for i in self._repository.load().items if str(i.id).startswith(prefix)]
        if not matches:
            raise WorkspaceError(f"No saved item with id starting '{prefix}'.")
        if len(matches) > 1:
            raise WorkspaceError(f"Id '{prefix}' matches {len(matches)} items; use more characters.")
        return matches[0]

    def remove_item(self, item_id: str) -> SavedItem:
        target = self.get_item(item_id)
        workspace = self._repository.load()
        workspace.remove(target.id)
        self._repository.save(workspace)
        return target

    def search(self, query: str) -> list[SavedItem]:
        return self._repository.load().search(query)

    @staticmethod
    def document_id_of(item: SavedItem) -> UUID | None:
        """The library document a saved item comes from, if any, so it can
        be reopened in the reader."""
        if item.kind not in (SavedItemKind.DOCUMENT, SavedItemKind.PASSAGE):
            return None
        try:
            return UUID(item.reference.split("#", 1)[0])
        except ValueError:
            return None

    @staticmethod
    def paragraph_of(item: SavedItem) -> int | None:
        """For a saved passage, its paragraph number (from the ``¶n`` locator)."""
        if item.kind is not SavedItemKind.PASSAGE or "#¶" not in item.reference:
            return None
        number = item.reference.rsplit("#¶", 1)[1]
        return int(number) if number.isdigit() else None


def render_answer(response: AgentResponse) -> str:
    """Plain-text snapshot of an answer: explanation (marked as AI), then
    each source with its citation and the quoted text."""
    parts = []
    if response.explanation:
        parts.append(f"Explanation (AI-generated):\n{response.explanation}")
    if response.sources:
        parts.append(
            "Sources:\n"
            + "\n\n".join(
                f"{s.label} {s.citation.format()}\n{s.citation.quoted_text}"
                for s in response.sources
            )
        )
    parts.extend(f"Note: {warning}" for warning in response.warnings)
    return "\n\n".join(parts)
