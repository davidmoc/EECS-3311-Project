import pytest

from praxis.documents import Book
from praxis.persistence import Database, SQLDocumentRepository
from praxis.tools import (
    LibrarySearchTool,
    PassageSearchTool,
    Tool,
    ToolFactory,
    ToolManager,
    ToolResult,
    ToolType,
)


class RecordingTool(Tool):
    """Accepts only {'ok': True}; records what it was executed with."""

    name = "recording"
    description = "test tool"

    def __init__(self, error=None):
        self.executed_with = []
        self._error = error

    def validate(self, tool_input):
        return tool_input.get("ok") is True

    def execute(self, tool_input):
        self.executed_with.append(tool_input)
        if self._error:
            raise self._error
        return ToolResult.ok(self.name, ["result"])


@pytest.fixture
def repository():
    database = Database()
    repository = SQLDocumentRepository(database)
    for number in range(1, 8):
        repository.save(Book(title=f"Wage Labour Study {number}", author="Author"))
    repository.save(Book(title="State and Revolution", author="V. I. Lenin"))
    yield repository
    database.close()


# --- ToolManager -----------------------------------------------------------


def test_registered_tool_is_executed_and_counted():
    manager, tool = ToolManager(), RecordingTool()
    manager.register_tool(tool)

    result = manager.execute_tool("recording", {"ok": True})

    assert result == ToolResult(tool_name="recording", success=True, items=("result",))
    assert tool.executed_with == [{"ok": True}]
    assert manager.call_count == 1


def test_unknown_tool_is_a_failed_result_not_an_exception():
    result = ToolManager().execute_tool("missing", {})

    assert not result.success
    assert "missing" in result.error


@pytest.mark.parametrize("bad_input", [{}, {"ok": False}, None, "ok"])
def test_invalid_input_is_rejected_without_executing(bad_input):
    manager, tool = ToolManager(), RecordingTool()
    manager.register_tool(tool)

    result = manager.execute_tool("recording", bad_input)

    assert not result.success
    assert tool.executed_with == []
    assert manager.call_count == 0


def test_tool_crash_is_contained_as_a_failed_result():
    manager = ToolManager()
    manager.register_tool(RecordingTool(error=RuntimeError("network down")))

    result = manager.execute_tool("recording", {"ok": True})

    assert not result.success
    assert "network down" in result.error
    assert manager.call_count == 1


def test_duplicate_tool_names_are_rejected():
    manager = ToolManager()
    manager.register_tool(RecordingTool())

    with pytest.raises(ValueError):
        manager.register_tool(RecordingTool())


def test_empty_result_is_distinguished_from_failure():
    assert ToolResult.ok("t", []).is_empty
    assert not ToolResult.ok("t", [1]).is_empty
    assert not ToolResult.failure("t", "boom").is_empty


# --- LibrarySearchTool -----------------------------------------------------


def test_library_search_returns_matching_documents(repository):
    result = LibrarySearchTool(repository).execute({"query": "revolution"})

    assert result.success
    assert [d.title for d in result.items] == ["State and Revolution"]


def test_library_search_applies_default_and_explicit_limits(repository):
    tool = LibrarySearchTool(repository)

    assert len(tool.execute({"query": "wage"}).items) == 5
    assert len(tool.execute({"query": "wage", "limit": 2}).items) == 2
    assert len(tool.execute({"query": "wage", "limit": 50}).items) == 7


def test_library_search_with_no_matches_is_successful_but_empty(repository):
    assert LibrarySearchTool(repository).execute({"query": "feudalism"}).is_empty


@pytest.mark.parametrize(
    "tool_input",
    [
        {},
        {"query": ""},
        {"query": "   "},
        {"query": 42},
        {"query": "wage", "limit": 0},
        {"query": "wage", "limit": 51},
        {"query": "wage", "limit": "3"},
        {"query": "wage", "limit": True},
    ],
)
def test_library_search_rejects_invalid_input(repository, tool_input):
    assert LibrarySearchTool(repository).validate(tool_input) is False


# --- ToolFactory with ToolManager -----------------------------------------


def test_factory_creates_tools_that_work_through_the_manager(repository):
    factory, manager = ToolFactory(repository), ToolManager()
    for tool in factory.create_all():
        manager.register_tool(tool)

    assert manager.tool_names() == ["library_search", "passage_search", "source_retrieval"]
    assert isinstance(factory.create_tool(ToolType.LIBRARY_SEARCH), LibrarySearchTool)
    assert isinstance(factory.create_tool(ToolType.PASSAGE_SEARCH), PassageSearchTool)

    result = manager.execute_tool("library_search", {"query": "lenin"})
    assert [d.title for d in result.items] == ["State and Revolution"]

    rejected = manager.execute_tool("library_search", {"query": ""})
    assert not rejected.success


def test_factory_rejects_unknown_tool_types(repository):
    with pytest.raises(ValueError):
        ToolFactory(repository).create_tool("web_search")


# --- PassageSearchTool -----------------------------------------------------


def test_passage_search_returns_cited_passages_through_the_manager():
    database = Database()
    repository = SQLDocumentRepository(database)
    repository.save(
        Book(
            title="Wage Labour and Capital",
            author="Karl Marx",
            text="Wages are not the worker's share in the commodities he produces.",
        )
    )
    manager = ToolManager()
    manager.register_tool(PassageSearchTool(repository))

    result = manager.execute_tool("passage_search", {"query": "what are wages?"})
    database.close()

    assert result.success
    [match] = result.items
    assert match.document.title == "Wage Labour and Capital"
    assert match.passage.locator == "¶1"


@pytest.mark.parametrize(
    "tool_input",
    [{}, {"query": "  "}, {"query": 3}, {"query": "x", "limit": 0},
     {"query": "x", "limit": 21}, {"query": "x", "limit": True}],
)
def test_passage_search_rejects_bad_input(repository, tool_input):
    assert PassageSearchTool(repository).validate(tool_input) is False
