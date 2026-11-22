"""The evidence gathered while answering a question or researching a topic.

Each source gets a number the first time it is added. The LLM is asked to
cite by that number (``[2]``), which lets the agent check every reference
in the answer against material that was actually retrieved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from praxis.documents import Citation, Document, Passage

# "[2]" or "[1, 3]" in model output.
CITATION_MARK = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def cited_numbers(text: str) -> list[int]:
    """Source numbers cited in ``text``, each once, in order of first mention."""
    numbers: dict[int, None] = {}
    for group in CITATION_MARK.findall(text):
        for number in group.split(","):
            numbers.setdefault(int(number), None)
    return list(numbers)


@dataclass(frozen=True)
class Source:
    number: int
    passage: Passage
    citation: Citation

    @property
    def label(self) -> str:
        return f"[{self.number}]"


class ResearchCorpus:
    def __init__(self) -> None:
        self._documents: dict[UUID, Document] = {}
        self._sources: list[Source] = []
        self._numbers: dict[UUID, int] = {}  # passage id -> source number

    def add_document(self, document: Document) -> None:
        self._documents.setdefault(document.id, document)

    def add_passage(self, document: Document, passage: Passage) -> Source:
        """Add ``passage`` with a citation, or return it if already added.

        The citation is created by the document, so the licence's quotation
        limit applies to everything the corpus hands out.
        """
        if passage.id in self._numbers:
            return self.source(self._numbers[passage.id])
        self.add_document(document)
        return self.add_citation(passage, document.cite(passage))

    def add_citation(self, passage: Passage, citation: Citation) -> Source:
        if citation.document_id != passage.document_id:
            raise ValueError("Citation does not refer to this passage's document.")
        if passage.id in self._numbers:
            return self.source(self._numbers[passage.id])
        source = Source(len(self._sources) + 1, passage, citation)
        self._sources.append(source)
        self._numbers[passage.id] = source.number
        return source

    def source(self, number: int) -> Source:
        if not 1 <= number <= len(self._sources):
            raise KeyError(f"There is no source [{number}].")
        return self._sources[number - 1]

    def has_source(self, number: int) -> bool:
        return 1 <= number <= len(self._sources)

    @property
    def sources(self) -> list[Source]:
        return list(self._sources)

    @property
    def documents(self) -> list[Document]:
        return list(self._documents.values())

    def __len__(self) -> int:
        return len(self._sources)

    @property
    def is_empty(self) -> bool:
        return not self._sources
