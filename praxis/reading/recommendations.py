"""Reading recommendations (F07, UC07, SD05's ``recommendReadings``).

The library is searched for texts on the reader's topic; the model ranks
the texts found and says why each is worth reading. Texts the reader has
finished are moved to the end (UC07 step 4). Without a model, the texts
are ranked by how many of their passages matched, and the reader is told.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from praxis.agent.prompts import DIFFICULTIES, MAX_EXTERNAL_SUGGESTIONS, MAX_RECOMMENDATIONS
from praxis.documents import Citation, Document

# "recommend: [2] | introductory | why" and "external: title | author | why",
# optionally bulleted.
_RECOMMEND_LINE = re.compile(
    r"^\s*(?:[-*•]\s*)?recommend\s*:\s*\[(\d+)\]\s*\|\s*([^|]*?)\s*\|\s*(.+?)\s*$",
    re.IGNORECASE,
)
_EXTERNAL_LINE = re.compile(
    r"^\s*(?:[-*•]\s*)?external\s*:\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*(.+?)\s*$",
    re.IGNORECASE,
)


class ReadingStatus(Enum):
    UNREAD = "unread"
    IN_PROGRESS = "in progress"
    COMPLETED = "completed"
    UNKNOWN = "unknown"  # personalization is off, so history is not consulted


@dataclass(frozen=True)
class Recommendation:
    """A library text recommended for a topic.

    ``reason`` is the model's (AI-generated) unless ``ranked_by_model`` on
    the result is False, when it only reports how the text matched.
    ``passages`` are where the topic comes up, so the reader can start
    there. ``difficulty`` is the model's estimate, or None.
    """

    document: Document
    reason: str
    passages: tuple[Citation, ...] = ()
    difficulty: str | None = None
    status: ReadingStatus = ReadingStatus.UNKNOWN
    progress: float = 0.0


@dataclass(frozen=True)
class ExternalSuggestion:
    """A work the model named that is not in the library (UC07: "external
    source recommendations may be shown"). Not checked against anything."""

    title: str
    author: str
    reason: str


@dataclass(frozen=True)
class RecommendationResult:
    topic: str
    recommendations: tuple[Recommendation, ...] = ()
    external: tuple[ExternalSuggestion, ...] = ()
    ranked_by_model: bool = False
    personalized: bool = False
    # Texts that matched the topic but were not recommended.
    passed_over: int = 0
    warnings: tuple[str, ...] = ()
    tokens_used: int = 0


@dataclass(frozen=True)
class ParsedRecommendations:
    ranked: tuple[tuple[int, str | None, str], ...]  # (candidate, difficulty, reason)
    external: tuple[ExternalSuggestion, ...]
    unknown: tuple[int, ...]  # candidate numbers the model invented


def parse_recommendations(text: str, candidates: int) -> ParsedRecommendations | None:
    """The model's ranking, or None if no line is in the reply format.

    Each candidate is kept once, at its best rank. Numbers outside
    ``1..candidates`` are returned as ``unknown``. A difficulty that is not
    one of ``DIFFICULTIES`` becomes None rather than invalidating the line.
    """
    ranked: dict[int, tuple[int, str | None, str]] = {}
    external: list[ExternalSuggestion] = []
    unknown: dict[int, None] = {}
    readable = False
    for line in text.splitlines():
        if match := _RECOMMEND_LINE.match(line):
            readable = True
            number, difficulty, reason = int(match[1]), match[2].lower(), match[3]
            if not 1 <= number <= candidates:
                unknown.setdefault(number, None)
                continue
            if number not in ranked and len(ranked) < MAX_RECOMMENDATIONS:
                ranked[number] = (number, difficulty if difficulty in DIFFICULTIES else None, reason)
        elif match := _EXTERNAL_LINE.match(line):
            readable = True
            if len(external) < MAX_EXTERNAL_SUGGESTIONS:
                external.append(ExternalSuggestion(match[1], match[2], match[3]))
    if not readable:
        return None
    return ParsedRecommendations(tuple(ranked.values()), tuple(external), tuple(unknown))
