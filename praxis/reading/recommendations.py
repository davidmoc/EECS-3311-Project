"""Reading recommendations (F07, UC07, SD05's ``recommendReadings``).

The library is searched for texts on the reader's topic; the model ranks
the texts found and says why each is worth reading. Texts the reader has
finished are moved to the end (UC07 step 4). Without a model, the texts
are ranked by how many of their passages matched, and the reader is told.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from uuid import UUID

from praxis.agent.prompts import (
    DIFFICULTIES,
    MAX_EXTERNAL_SUGGESTIONS,
    MAX_RECOMMENDATIONS,
    PromptBuilder,
    reader_context,
)
from praxis.documents import Citation, Document, NewsArticle
from praxis.llm import LLMClient, LLMError
from praxis.reader_model import ReaderProfile
from praxis.tools import ToolManager

PASSAGE_SEARCH = "passage_search"
# Passages searched for per query; the tool allows at most 20.
SEARCH_LIMIT = 20
# Texts shown to the model, and passages shown per text.
MAX_CANDIDATES = 8
PASSAGES_PER_CANDIDATE = 2
EXCERPT_CHARS = 300
# Interests a "what should I read next" request is based on.
INTERESTS_USED = 3

NO_LLM_WARNING = (
    "No language model is configured (set OPENAI_API_KEY), so the texts are "
    "ranked by how many of their passages match, with no reasons or difficulty."
)
UNREADABLE_WARNING = (
    "The model's ranking could not be read, so the texts are ranked by how "
    "many of their passages match."
)
SPARSE_PROFILE_WARNING = (
    "Little is known about your reading and knowledge yet, so these "
    "recommendations rest on the topic alone, not on you."
)
PERSONALIZATION_OFF_WARNING = (
    "Personalization is off, so these recommendations rest on the topic "
    "alone and your reading history was not consulted."
)
NO_CANDIDATES_WARNING = "No text in the library discusses this topic."
NO_INTERESTS_ERROR = (
    "Nothing is known about your interests yet. Name a topic "
    "(praxis recommend \"...\"), or add an interest with praxis profile interest."
)
PERSONALIZATION_OFF_ERROR = (
    "Personalization is off, so there is nothing to base recommendations on. "
    "Name a topic instead."
)

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


class RecommendationError(Exception):
    """No recommendations could be made; the message says why."""


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


@dataclass
class _Candidate:
    document: Document
    passages: list[Citation]
    hits: int = 0


class RecommendationService:
    """SD05's ``RecommendationService``: ``recommend_readings(topic, profile)``
    and ``recommend_next(profile)``."""

    def __init__(
        self,
        tools: ToolManager,
        llm: LLMClient | None = None,
        prompts: PromptBuilder | None = None,
    ) -> None:
        self._tools = tools
        self._llm = llm
        self._prompts = prompts or PromptBuilder()

    def recommend_readings(
        self, topic: str, profile: ReaderProfile | None = None
    ) -> RecommendationResult:
        """Texts to read on ``topic``, best first, each with why."""
        topic = " ".join(topic.split())
        if not topic:
            raise RecommendationError("Name a topic or question to get recommendations for.")
        return self._recommend(topic, [topic], profile)

    def recommend_next(self, profile: ReaderProfile) -> RecommendationResult:
        """Texts to read next, from the reader's strongest interests
        (F07: "browse personalized recommendations")."""
        if not profile.personalization_enabled:
            raise RecommendationError(PERSONALIZATION_OFF_ERROR)
        interests = profile.interests.top(INTERESTS_USED)
        if not interests:
            raise RecommendationError(NO_INTERESTS_ERROR)
        return self._recommend(", ".join(interests), interests, profile)

    def _recommend(
        self, topic: str, queries: list[str], profile: ReaderProfile | None
    ) -> RecommendationResult:
        warnings: list[str] = []
        candidates = self._find_candidates(queries, warnings)
        uses_history = profile is not None and profile.personalization_enabled
        if profile is not None and not profile.personalization_enabled:
            warnings.append(PERSONALIZATION_OFF_WARNING)
        elif profile is None or profile.is_sparse:
            warnings.append(SPARSE_PROFILE_WARNING)
        if not candidates:
            warnings.append(NO_CANDIDATES_WARNING)

        def status(document: Document) -> tuple[ReadingStatus, float]:
            if not uses_history:
                return ReadingStatus.UNKNOWN, 0.0
            record = profile.history.get(document.id)
            if record is None:
                return ReadingStatus.UNREAD, 0.0
            if record.completed:
                return ReadingStatus.COMPLETED, 1.0
            return ReadingStatus.IN_PROGRESS, record.progress

        def by_matches(note: str) -> RecommendationResult:
            warnings.append(note)
            recommendations = [
                Recommendation(
                    c.document,
                    f"{c.hits} passage{'s' if c.hits != 1 else ''} match{'es' if c.hits == 1 else ''} the topic.",
                    tuple(c.passages), None, *status(c.document),
                )
                for c in candidates[:MAX_RECOMMENDATIONS]
            ]
            return RecommendationResult(
                topic, _finished_last(recommendations),
                passed_over=max(0, len(candidates) - MAX_RECOMMENDATIONS),
                warnings=tuple(warnings),
            )

        if self._llm is None:
            return by_matches(NO_LLM_WARNING) if candidates else RecommendationResult(
                topic, warnings=(*warnings, NO_LLM_WARNING)
            )

        described = [
            (f"[{n}] {_heading(c.document)}", _body(c, *status(c.document), uses_history))
            for n, c in enumerate(candidates, start=1)
        ]
        prompt = self._prompts.build_recommendation_prompt(topic, described, profile)
        try:
            response = self._llm.generate(prompt)
        except LLMError as exc:
            note = f"The texts could not be ranked by the model ({exc}), so they are ranked by how many of their passages match."
            return by_matches(note) if candidates else RecommendationResult(
                topic, warnings=(*warnings, f"The model could not be asked: {exc}")
            )

        parsed = parse_recommendations(response.text, len(candidates))
        if parsed is None:
            return replace(by_matches(UNREADABLE_WARNING), tokens_used=response.total_tokens)
        if parsed.unknown:
            labels = ", ".join(f"[{n}]" for n in parsed.unknown)
            warnings.append(
                f"The model recommended {labels}, which {'is' if len(parsed.unknown) == 1 else 'are'} "
                "not among the texts found; ignored."
            )
        recommendations = [
            Recommendation(
                candidates[number - 1].document, reason,
                tuple(candidates[number - 1].passages), difficulty,
                *status(candidates[number - 1].document),
            )
            for number, difficulty, reason in parsed.ranked
        ]
        return RecommendationResult(
            topic,
            _finished_last(recommendations),
            parsed.external,
            ranked_by_model=True,
            personalized=reader_context(profile) is not None,
            passed_over=len(candidates) - len(recommendations),
            warnings=tuple(warnings),
            tokens_used=response.total_tokens,
        )

    def _find_candidates(self, queries: list[str], warnings: list[str]) -> list[_Candidate]:
        """Library texts (not news) with passages matching any query: those
        tagged with a query first, then by how many passages matched."""
        found: dict[UUID, _Candidate] = {}
        for query in queries:
            result = self._tools.execute_tool(PASSAGE_SEARCH, {"query": query, "limit": SEARCH_LIMIT})
            if not result.success:
                warnings.append(f"Library search failed: {result.error}")
                continue
            for match in result.items:
                document = match.document
                if document.kind == NewsArticle.kind:
                    continue
                candidate = found.setdefault(document.id, _Candidate(document, []))
                candidate.hits += 1
                if len(candidate.passages) < PASSAGES_PER_CANDIDATE:
                    citation = document.cite(match.passage)
                    if citation.locator not in {c.locator for c in candidate.passages}:
                        candidate.passages.append(citation)
        # Texts the catalogue tags with the topic come first: word matches
        # alone can mislead (the index stems "imperialism" to match
        # "Imperial Diet"). Sorting is stable, so the first found wins ties.
        wanted = {" ".join(q.lower().split()) for q in queries}
        ranked = sorted(
            found.values(),
            key=lambda c: (not wanted & {t.lower() for t in c.document.topics}, -c.hits),
        )
        return ranked[:MAX_CANDIDATES]


def _finished_last(recommendations: list[Recommendation]) -> tuple[Recommendation, ...]:
    """UC07 step 4: texts the reader finished go after the rest, otherwise
    in the same order."""
    return tuple(sorted(recommendations, key=lambda r: r.status is ReadingStatus.COMPLETED))


def _heading(document: Document) -> str:
    year = f" ({document.publication_date.year})" if document.publication_date else ""
    return f"{document.author}, “{document.title}”{year}, {document.kind}"


def _body(candidate: _Candidate, status: ReadingStatus, progress: float, uses_history: bool) -> str:
    lines = []
    if candidate.document.topics:
        lines.append(f"Topics: {', '.join(candidate.document.topics)}")
    if uses_history:
        lines.append({
            ReadingStatus.UNREAD: "Reader: has not opened it",
            ReadingStatus.IN_PROGRESS: f"Reader: has read {progress:.0%} of it",
            ReadingStatus.COMPLETED: "Reader: has finished it",
        }[status])
    lines.append(f"Matching passages: {candidate.hits}")
    for citation in candidate.passages:
        text = citation.quoted_text
        if len(text) > EXCERPT_CHARS:
            text = text[:EXCERPT_CHARS].rstrip() + "…"
        lines.append(f"{citation.locator}: {text}")
    return "\n".join(lines)
