"""What every agent tool looks like to the rest of the system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """Outcome of one tool call. Failures are values, not exceptions, so the
    agent can inspect them and decide whether to retry or change plan."""

    tool_name: str
    success: bool
    items: tuple[Any, ...] = ()
    error: str | None = None

    @classmethod
    def ok(cls, tool_name: str, items: list[Any] | tuple[Any, ...]) -> ToolResult:
        return cls(tool_name=tool_name, success=True, items=tuple(items))

    @classmethod
    def failure(cls, tool_name: str, error: str) -> ToolResult:
        return cls(tool_name=tool_name, success=False, error=error)

    @property
    def is_empty(self) -> bool:
        return self.success and not self.items


class Tool(ABC):
    name: str
    description: str

    @abstractmethod
    def validate(self, tool_input: dict[str, Any]) -> bool:
        """Whether ``tool_input`` is acceptable. Must not have side effects."""

    @abstractmethod
    def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        """Run the tool. Only called with input that passed ``validate``."""
