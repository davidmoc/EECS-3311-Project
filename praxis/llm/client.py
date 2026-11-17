"""The application's own view of a language model.

Everything else in the system depends on ``LLMClient`` and these plain data
types, never on a vendor SDK. Adapters translate to and from a provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class LLMError(Exception):
    """The model could not produce a usable response."""


@dataclass(frozen=True)
class Prompt:
    user: str
    system: str = ""

    def __post_init__(self) -> None:
        if not self.user.strip():
            raise ValueError("A prompt needs user content.")


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: Prompt) -> LLMResponse:
        """Return the model's response, or raise ``LLMError``."""
