"""The queue of research commands still to run (F03)."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from praxis.research.commands import ResearchCommand
from praxis.research.session import ResearchError


class ResearchPlan:
    def __init__(self, objective: str, commands: Iterable[ResearchCommand] = ()) -> None:
        self.objective = objective
        # A deque is a double-ended queue: cheap to add or remove at both ends.
        self._commands: deque[ResearchCommand] = deque()
        for command in commands:
            self.add_command(command)

    def add_command(self, command: ResearchCommand) -> None:
        """Queue ``command`` last, unless the same action is already queued."""
        if command not in self._commands:
            self._commands.append(command)

    def add_first(self, command: ResearchCommand) -> None:
        """Queue ``command`` to run next (used for retries)."""
        self._commands.appendleft(command)

    def get_next_command(self) -> ResearchCommand:
        if not self._commands:
            raise ResearchError("The research plan has no commands left.")
        return self._commands.popleft()

    def replace_commands(self, commands: Iterable[ResearchCommand]) -> None:
        self._commands.clear()
        for command in commands:
            self.add_command(command)

    def is_complete(self) -> bool:
        return not self._commands

    @property
    def pending(self) -> list[ResearchCommand]:
        return list(self._commands)

    def __len__(self) -> int:
        return len(self._commands)
