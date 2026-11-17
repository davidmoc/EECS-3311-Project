"""Tool that searches the local reading library."""

from __future__ import annotations

from typing import Any

from praxis.persistence import DocumentRepository
from praxis.tools.base import Tool, ToolResult

DEFAULT_LIMIT = 5
MAX_LIMIT = 50


class LibrarySearchTool(Tool):
    name = "library_search"
    description = (
        "Search the reading library for texts by title, author, topic or "
        "content. Input: {'query': str, 'limit': int (optional)}."
    )

    def __init__(self, documents: DocumentRepository) -> None:
        self._documents = documents

    def validate(self, tool_input: dict[str, Any]) -> bool:
        query = tool_input.get("query")
        if not isinstance(query, str) or not query.strip():
            return False
        limit = tool_input.get("limit", DEFAULT_LIMIT)
        # bool is an int subclass; True must not pass as a limit of 1
        return (
            isinstance(limit, int)
            and not isinstance(limit, bool)
            and 1 <= limit <= MAX_LIMIT
        )

    def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        limit = tool_input.get("limit", DEFAULT_LIMIT)
        matches = self._documents.search(tool_input["query"])
        return ToolResult.ok(self.name, matches[:limit])
