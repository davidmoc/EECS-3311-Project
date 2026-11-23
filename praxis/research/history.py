"""Historical context (F09, UC09).

The model first judges whether the topic is narrow enough and plans
searches from its origins onward; the library is then searched with
``TraceHistoricalDevelopmentCommand``; finally the model organises the
passages into origins, dated stages and turning points, continuities and
disputed interpretations, each citing its passages. Facts and
interpretations are kept apart (UC09: "distinguishes factual chronology
from contested interpretation"), and what the passages do not cover is
listed as gaps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from praxis.agent.corpus import Source, cited_numbers
from praxis.agent.prompts import MAX_HISTORY_SEARCHES

_CITATIONS = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")
_LINE = re.compile(
    r"^\s*(?:[-*•]\s*)?(overview|origin|stage|turning point|continuity|interpretation|gap)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
_SCOPE_LINE = re.compile(r"^\s*(?:[-*•]\s*)?scope\s*:\s*([^|]+?)\s*(?:\|\s*(.*?)\s*)?$", re.IGNORECASE)
_SEARCH_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])?\s*search\s*:\s*([^|]+?)\s*\|\s*(.+?)\s*$", re.IGNORECASE)
MAX_ITEMS_PER_KIND = 6


class HistoryItemKind(Enum):
    ORIGIN = "origin"
    STAGE = "stage"
    TURNING_POINT = "turning point"
    CONTINUITY = "continuity"
    INTERPRETATION = "interpretation"

    @property
    def is_dated(self) -> bool:
        return self in (HistoryItemKind.STAGE, HistoryItemKind.TURNING_POINT)


class ContextStatus(Enum):
    EXPLAINED = "explained"
    TOO_BROAD = "too broad"  # UC09: "the system may ask the user to narrow the scope"
    NO_SOURCES = "no sources"
    NOT_ORGANISED = "not organised"  # passages found, but no usable account


@dataclass(frozen=True)
class HistoryItem:
    kind: HistoryItemKind
    text: str  # without its citation marks
    evidence: tuple[int, ...]  # source numbers
    when: str = ""  # stages and turning points only


@dataclass(frozen=True)
class SuggestedReading:
    """A text the account drew on, to read further (UC09 step 6)."""

    document_id: UUID
    title: str
    author: str
    start: str  # locator of the first passage cited from it
    cited: int  # how many of its passages the account cites


@dataclass(frozen=True)
class HistoryPlan:
    too_broad: bool
    narrower: tuple[str, ...]
    searches: tuple[tuple[str, str], ...]  # (period or aspect, keywords)


@dataclass(frozen=True)
class ParsedHistory:
    overview: str
    overview_evidence: tuple[int, ...]
    items: tuple[HistoryItem, ...]
    gaps: tuple[str, ...]


@dataclass(frozen=True)
class HistoricalContext:
    topic: str
    status: ContextStatus
    overview: str = ""
    overview_evidence: tuple[int, ...] = ()
    items: tuple[HistoryItem, ...] = ()
    gaps: tuple[str, ...] = ()
    narrower: tuple[str, ...] = ()
    sources: tuple[Source, ...] = ()
    purposes: dict[int, str] | None = None
    steps: tuple[str, ...] = ()
    readings: tuple[SuggestedReading, ...] = ()
    personalized: bool = False
    warnings: tuple[str, ...] = ()
    tokens_used: int = 0

    def of_kind(self, kind: HistoryItemKind) -> list[HistoryItem]:
        return [item for item in self.items if item.kind is kind]

    @property
    def cited(self) -> tuple[Source, ...]:
        numbers = set(self.overview_evidence)
        for item in self.items:
            numbers.update(item.evidence)
        return tuple(s for s in self.sources if s.number in numbers)


def parse_history_plan(text: str) -> HistoryPlan | None:
    """The model's scope judgement and searches, or None if no line is in
    the reply format. Searches beyond ``MAX_HISTORY_SEARCHES`` are dropped."""
    too_broad, narrower, searches, readable = False, (), [], False
    for line in text.splitlines():
        if match := _SCOPE_LINE.match(line):
            readable = True
            too_broad = "broad" in match[1].lower()
            narrower = tuple(t.strip() for t in (match[2] or "").split(";") if t.strip())
        elif match := _SEARCH_LINE.match(line):
            readable = True
            if len(searches) < MAX_HISTORY_SEARCHES:
                searches.append((match[1], match[2]))
    if not readable:
        return None
    return HistoryPlan(too_broad, narrower if too_broad else (), tuple(searches))


def parse_history(text: str) -> ParsedHistory | None:
    """The organised account, or None if no line is in the reply format.

    Citation marks are taken out of each item's text and kept as its
    evidence. A stage or turning point without "when |" is "undated".
    """
    overview, overview_evidence = [], []
    items: list[HistoryItem] = []
    gaps: list[str] = []
    counts: dict[HistoryItemKind, int] = {}
    readable = False
    for line in text.splitlines():
        match = _LINE.match(line)
        if not match:
            continue
        readable = True
        label, body = match[1].lower(), match[2]
        if label == "gap":
            gaps.append(body)
            continue
        evidence = tuple(cited_numbers(body))
        clean = strip_citations(body)
        if label == "overview":
            overview.append(clean)
            overview_evidence.extend(n for n in evidence if n not in overview_evidence)
            continue
        kind = HistoryItemKind(label)
        if counts.get(kind, 0) >= MAX_ITEMS_PER_KIND:
            continue
        counts[kind] = counts.get(kind, 0) + 1
        when = ""
        if kind.is_dated:
            when, bar, rest = clean.partition("|")
            when, clean = (when.strip(), rest.strip()) if bar else ("undated", clean)
        items.append(HistoryItem(kind, clean, evidence, when))
    if not readable:
        return None
    return ParsedHistory(" ".join(overview), tuple(overview_evidence), tuple(items), tuple(gaps))


def check_items(
    items: tuple[HistoryItem, ...], known: set[int]
) -> tuple[list[HistoryItem], int]:
    """Items with their evidence limited to retrieved sources; items left
    citing nothing are dropped and counted (UC09 step 4: "Evidence
    supporting those developments is retained")."""
    kept, dropped = [], 0
    for item in items:
        evidence = tuple(n for n in item.evidence if n in known)
        if not evidence:
            dropped += 1
            continue
        kept.append(HistoryItem(item.kind, item.text, evidence, item.when))
    return kept, dropped


def suggested_readings(cited: tuple[Source, ...]) -> tuple[SuggestedReading, ...]:
    """The texts behind ``cited``, most cited first, each with the first
    passage cited from it. The caller leaves out news reports."""
    by_document: dict[UUID, list[Source]] = {}
    for source in cited:
        by_document.setdefault(source.citation.document_id, []).append(source)
    readings = [
        SuggestedReading(
            document_id, sources[0].citation.document_title, sources[0].citation.author,
            sources[0].citation.locator, len(sources),
        )
        for document_id, sources in by_document.items()
    ]
    return tuple(sorted(readings, key=lambda r: -r.cited))


def strip_citations(text: str) -> str:
    stripped = _CITATIONS.sub("", text)
    stripped = re.sub(r"\(\s*\)", "", stripped)
    return re.sub(r"\s+([.,;:])", r"\1", stripped).strip()
