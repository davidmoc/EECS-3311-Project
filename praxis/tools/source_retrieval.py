"""Tool that retrieves passages of one chosen source (F10, SD06's
"executeTool(source retrieval)").

The reader picks the sources to compare, so retrieval is per source: either
the paragraphs the reader named, or the source's passages that best match
the subject of the comparison.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from praxis.persistence import DocumentRepository, PassageMatch
from praxis.tools.base import Tool, ToolResult

DEFAULT_LIMIT = 3
MAX_LIMIT = 12


class SourceRetrievalTool(Tool):
    name = "source_retrieval"
    description = (
        "Retrieve passages of one source document: the paragraphs named in "
        "'paragraphs', or the passages that best match 'query'. Returns "
        "PassageMatch items. Input: {'document_id': str, 'query': str "
        "(optional), 'paragraphs': list[int] (optional), 'limit': int (optional)}."
    )

    def __init__(self, documents: DocumentRepository) -> None:
        self._documents = documents

    def validate(self, tool_input: dict[str, Any]) -> bool:
        try:
            UUID(str(tool_input.get("document_id")))
        except ValueError:
            return False
        query = tool_input.get("query")
        paragraphs = tool_input.get("paragraphs")
        if query is None and paragraphs is None:
            return False
        if query is not None and not (isinstance(query, str) and query.strip()):
            return False
        if paragraphs is not None and not (
            isinstance(paragraphs, list)
            and paragraphs
            and all(_is_int(n) and n >= 1 for n in paragraphs)
        ):
            return False
        limit = tool_input.get("limit", DEFAULT_LIMIT)
        return _is_int(limit) and 1 <= limit <= MAX_LIMIT

    def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        document_id = UUID(str(tool_input["document_id"]))
        limit = tool_input.get("limit", DEFAULT_LIMIT)
        paragraphs = tool_input.get("paragraphs")
        if not paragraphs:
            if self._documents.find_by_id(document_id) is None:
                return ToolResult.failure(self.name, f"No source with id {document_id}.")
            return ToolResult.ok(
                self.name,
                self._documents.search_passages(tool_input["query"], limit, document_id),
            )

        document = self._documents.find_by_id(document_id)
        if document is None:
            return ToolResult.failure(self.name, f"No source with id {document_id}.")
        passages = document.passages()
        missing = [n for n in paragraphs if n > len(passages)]
        if missing:
            return ToolResult.failure(
                self.name,
                f"“{document.title}” has {len(passages)} paragraphs; there is no "
                + ", ".join(f"¶{n}" for n in missing) + ".",
            )
        chosen = list(dict.fromkeys(paragraphs))[:limit]
        return ToolResult.ok(
            self.name, [PassageMatch(passages[n - 1], document, 0.0) for n in chosen]
        )


def _is_int(value: Any) -> bool:
    """``True`` is an int in Python, so it is ruled out explicitly."""
    return isinstance(value, int) and not isinstance(value, bool)
