"""Storage for the reader's workspace."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from praxis.persistence.database import Database
from praxis.workspace import SavedItem, SavedItemKind, Workspace


class WorkspaceRepository(ABC):
    @abstractmethod
    def load(self) -> Workspace: ...

    @abstractmethod
    def save(self, workspace: Workspace) -> None:
        """Store exactly the items in ``workspace``; removed items are deleted."""


class SQLWorkspaceRepository(WorkspaceRepository):
    def __init__(self, database: Database) -> None:
        self._connection = database.connection

    def load(self) -> Workspace:
        rows = self._connection.execute("SELECT * FROM saved_items").fetchall()
        return Workspace(
            [
                SavedItem(
                    id=UUID(row["id"]),
                    kind=SavedItemKind(row["kind"]),
                    title=row["title"],
                    reference=row["reference"],
                    content=row["content"],
                    note=row["note"],
                    tags=tuple(json.loads(row["tags"])),
                    saved_at=datetime.fromisoformat(row["saved_at"]),
                )
                for row in rows
            ]
        )

    def save(self, workspace: Workspace) -> None:
        # One transaction: either the whole workspace is stored or none of it.
        with self._connection:
            self._connection.execute("DELETE FROM saved_items")
            self._connection.executemany(
                "INSERT INTO saved_items VALUES (?,?,?,?,?,?,?,?)",
                [
                    (
                        str(item.id),
                        item.kind.value,
                        item.title,
                        item.reference,
                        item.content,
                        item.note,
                        json.dumps(list(item.tags)),
                        item.saved_at.isoformat(),
                    )
                    for item in workspace.items
                ],
            )
