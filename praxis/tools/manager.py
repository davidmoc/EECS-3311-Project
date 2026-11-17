"""Registry and single entry point for running agent tools."""

from __future__ import annotations

from typing import Any

from praxis.tools.base import Tool, ToolResult


class ToolManager:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self.call_count = 0

    def register_tool(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"A tool named '{tool.name}' is already registered.")
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def execute_tool(self, name: str, tool_input: dict[str, Any]) -> ToolResult:
        """Validate, then run, the named tool.

        Never raises: unknown tools, rejected input and tool crashes all come
        back as failed results. Invalid input is rejected without the tool
        being executed and without counting as a call.
        """
        tool = self.get_tool(name)
        if tool is None:
            return ToolResult.failure(name, f"Unknown tool '{name}'.")
        if not isinstance(tool_input, dict) or not tool.validate(tool_input):
            return ToolResult.failure(name, f"Invalid input for tool '{name}'.")

        self.call_count += 1
        try:
            return tool.execute(tool_input)
        except Exception as exc:  # a failing tool must not take down the agent
            return ToolResult.failure(name, f"Tool '{name}' failed: {exc}")
