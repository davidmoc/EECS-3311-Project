"""The queue of research commands still to run (F03)."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from praxis.research.commands import ResearchCommand
from praxis.research.session import ResearchError


class ResearchPlan:
    """Commands still to run, plus a memory of those already taken, so a
    revised plan never repeats a search."""

    def __init__(
        self,
        objective: str,
        commands: Iterable[ResearchCommand] = (),
        taken: Iterable[ResearchCommand] = (),
    ) -> None:
        """``taken`` restores, for a continued session, the commands that
        earlier rounds already ran."""
        self.objective = objective
        # A deque is a double-ended queue: cheap to add or remove at both ends.
        self._commands: deque[ResearchCommand] = deque()
        self._taken: dict[tuple[type, str], ResearchCommand] = {}
        for command in taken:
            self._taken.setdefault(command.key, command)
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
        self._taken.setdefault(command.key, command)
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

    @property
    def taken(self) -> list[ResearchCommand]:
        """Each action already run, once, in the order first run."""
        return list(self._taken.values())

    def __len__(self) -> int:
        return len(self._commands)

    def __eq__(self, other: object) -> bool:
        """Same objective, same queue, same actions already run. (Defining
        ``__eq__`` makes Python drop the default hash, which is right for a
        mutable object.)"""
        if not isinstance(other, ResearchPlan):
            return NotImplemented
        return (self.objective, self.pending, self.taken) == (
            other.objective, other.pending, other.taken
        )
