"""The queue of research commands still to run (F03)."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from praxis.research.commands import ResearchCommand
from praxis.research.session import ResearchError


class ResearchPlan:
    """Commands still to run, plus a memory of those already taken, so a
    revised plan never repeats a search."""

    def __init__(self, objective: str, commands: Iterable[ResearchCommand] = ()) -> None:
        self.objective = objective
        # A deque is a double-ended queue: cheap to add or remove at both ends.
        self._commands: deque[ResearchCommand] = deque()
        self._taken: set[tuple[type, str]] = set()
        for command in commands:
            self.add_command(command)

    def add_command(self, command: ResearchCommand) -> bool:
        """Queue ``command`` last and return True, unless the same action is
        already queued or has already been run."""
        if command.key in self._taken or any(c.key == command.key for c in self._commands):
            return False
        self._commands.append(command)
        return True

    def add_first(self, command: ResearchCommand) -> None:
        """Queue ``command`` to run next (used for retries)."""
        self._commands.appendleft(command)

    def get_next_command(self) -> ResearchCommand:
        if not self._commands:
            raise ResearchError("The research plan has no commands left.")
        command = self._commands.popleft()
        self._taken.add(command.key)
        return command

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
