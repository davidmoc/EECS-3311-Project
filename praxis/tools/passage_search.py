"""Tool that finds the passages in the library that discuss a question."""

from __future__ import annotations

from typing import Any

from praxis.persistence import DocumentRepository
from praxis.tools.base import Tool, ToolResult

DEFAULT_LIMIT = 6
MAX_LIMIT = 20


class PassageSearchTool(Tool):
    name = "passage_search"
    description = (
        "Find the paragraphs in the reading library most relevant to a "
        "question or set of keywords. Returns PassageMatch items, best first. "
        "Input: {'query': str, 'limit': int (optional)}."
    )

    def __init__(self, documents: DocumentRepository) -> None:
        self._documents = documents

    def validate(self, tool_input: dict[str, Any]) -> bool:
        query = tool_input.get("query")
        if not isinstance(query, str) or not query.strip():
            return False
        limit = tool_input.get("limit", DEFAULT_LIMIT)
        return (
            isinstance(limit, int)
            and not isinstance(limit, bool)
            and 1 <= limit <= MAX_LIMIT
        )

    def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        limit = tool_input.get("limit", DEFAULT_LIMIT)
        return ToolResult.ok(
            self.name, self._documents.search_passages(tool_input["query"], limit)
        )
