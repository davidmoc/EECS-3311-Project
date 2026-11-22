"""Creation of agent tools.

Callers ask for a tool by type and never see how it is wired up, so adding a
tool means adding one creator here rather than touching the agent.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from praxis.persistence import DocumentRepository
from praxis.tools.base import Tool
from praxis.tools.library_search import LibrarySearchTool
from praxis.tools.passage_search import PassageSearchTool
from praxis.tools.source_retrieval import SourceRetrievalTool


class ToolType(Enum):
    LIBRARY_SEARCH = "library_search"
    PASSAGE_SEARCH = "passage_search"
    SOURCE_RETRIEVAL = "source_retrieval"


class ToolFactory:
    def __init__(self, documents: DocumentRepository) -> None:
        self._creators: dict[ToolType, Callable[[], Tool]] = {
            ToolType.LIBRARY_SEARCH: lambda: LibrarySearchTool(documents),
            ToolType.PASSAGE_SEARCH: lambda: PassageSearchTool(documents),
            ToolType.SOURCE_RETRIEVAL: lambda: SourceRetrievalTool(documents),
        }

    def create_tool(self, tool_type: ToolType) -> Tool:
        try:
            creator = self._creators[tool_type]
        except KeyError:
            raise ValueError(f"No tool is available for {tool_type!r}.") from None
        return creator()

    def create_all(self) -> list[Tool]:
        return [creator() for creator in self._creators.values()]
