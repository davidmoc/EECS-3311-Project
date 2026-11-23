"""Marxist theoretical analysis (F11, UC11; Stage 1's ``MaterialistAnalysis``).

Evidence is gathered (or reused from a research session), the model names
the concepts the evidence gives reason to apply, theoretical passages are
retrieved for them, and the model connects theory to evidence. Each part
of the analysis keeps the passages it rests on. Applications must cite
both a theory passage and an evidence passage; claims are marked
supported or tentative; other readings and the limits of a concept are
kept as their own kinds (UC11: "presents a tentative interpretation", "the
disagreement may be noted", "does not force every issue into a
predetermined category").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from praxis.agent.corpus import Source, cited_numbers
from praxis.agent.prompts import MAX_CONCEPTS
from praxis.research.history import SuggestedReading, strip_citations

THEORY_PURPOSE = "theory"
MAX_LINES_PER_KIND = 5
CONDITION_ASPECTS = (
    "material", "class", "production", "institution", "ideology", "development", "contradiction",
)

_CONCEPT_LINE = re.compile(
    r"^\s*(?:[-*•]|\d+[.)])?\s*concept\s*:\s*([^|]+?)\s*\|\s*([^|]*?)\s*(?:\|\s*(.*?)\s*)?$",
    re.IGNORECASE,
)
_ANALYSIS_LINE = re.compile(
    r"^\s*(?:[-*•]\s*)?(condition|application|claim|alternative|limit)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)


class AnalysisItemKind(Enum):
    CONDITION = "condition"
    APPLICATION = "application"
    CLAIM = "claim"
    ALTERNATIVE = "alternative"


class AnalysisStatus(Enum):
    ANALYSED = "analysed"
    NO_SOURCES = "no sources"
    NO_THEORY = "no theory"  # evidence found, but no theoretical passage
    NOT_ANALYSED = "not analysed"  # passages found, but no usable analysis


@dataclass(frozen=True)
class Concept:
    name: str
    keywords: str = ""
    reason: str = ""


@dataclass(frozen=True)
class AnalysisItem:
    kind: AnalysisItemKind
    text: str  # without its citation marks
    evidence: tuple[int, ...]
    # The condition's aspect, the application's concept, or a claim's
    # "supported"/"tentative".
    label: str = ""

    @property
    def is_tentative(self) -> bool:
        return self.kind is AnalysisItemKind.CLAIM and self.label != "supported"


@dataclass(frozen=True)
class ParsedAnalysis:
    items: tuple[AnalysisItem, ...]
    limits: tuple[str, ...]


@dataclass(frozen=True)
class MaterialistAnalysis:
    issue: str
    status: AnalysisStatus
    framework: str | None = None
    concepts: tuple[Concept, ...] = ()
    items: tuple[AnalysisItem, ...] = ()
    limits: tuple[str, ...] = ()
    sources: tuple[Source, ...] = ()
    purposes: dict[int, str] | None = None
    readings: tuple[SuggestedReading, ...] = ()  # theoretical texts to study
    research_session: str | None = None  # short id, if built on research
    personalized: bool = False
    warnings: tuple[str, ...] = ()
    tokens_used: int = 0

    def of_kind(self, kind: AnalysisItemKind) -> list[AnalysisItem]:
        return [item for item in self.items if item.kind is kind]

    @property
    def is_tentative(self) -> bool:
        """No claim is supported by several evidence passages."""
        claims = self.of_kind(AnalysisItemKind.CLAIM)
        return not claims or all(claim.is_tentative for claim in claims)

    @property
    def cited(self) -> tuple[Source, ...]:
        numbers = {n for item in self.items for n in item.evidence}
        return tuple(s for s in self.sources if s.number in numbers)


def parse_concepts(text: str) -> list[Concept]:
    """The concepts the model named, each once, at most ``MAX_CONCEPTS``."""
    concepts: dict[str, Concept] = {}
    for line in text.splitlines():
        if match := _CONCEPT_LINE.match(line):
            name = match[1].strip(" *\"'")
            if name and name.lower() not in concepts:
                concepts[name.lower()] = Concept(name, match[2], match[3] or "")
    return list(concepts.values())[:MAX_CONCEPTS]


def parse_analysis(text: str) -> ParsedAnalysis | None:
    """The analysis, or None if no line is in the reply format.

    "label | text" lines are split; a claim whose label is not "supported"
    is tentative, so a missing label never overstates a claim.
    """
    items: list[AnalysisItem] = []
    limits: list[str] = []
    counts: dict[AnalysisItemKind, int] = {}
    readable = False
    for line in text.splitlines():
        match = _ANALYSIS_LINE.match(line)
        if not match:
            continue
        readable = True
        name, body = match[1].lower(), match[2]
        if name == "limit":
            limits.append(strip_citations(body))
            continue
        kind = AnalysisItemKind(name)
        if counts.get(kind, 0) >= MAX_LINES_PER_KIND:
            continue
        counts[kind] = counts.get(kind, 0) + 1
        evidence = tuple(cited_numbers(body))
        clean = strip_citations(body)
        label = ""
        if kind is not AnalysisItemKind.ALTERNATIVE:
            head, bar, rest = clean.partition("|")
            if bar:
                label, clean = head.strip(), rest.strip()
        if kind is AnalysisItemKind.CLAIM:
            label = "supported" if label.lower() == "supported" else "tentative"
        elif kind is AnalysisItemKind.CONDITION:
            label = label.lower()
        items.append(AnalysisItem(kind, clean, evidence, label))
    if not readable:
        return None
    return ParsedAnalysis(tuple(items), tuple(limits))


def check_analysis(
    items: tuple[AnalysisItem, ...], purposes: dict[int, str], known: set[int]
) -> tuple[list[AnalysisItem], int]:
    """Items limited to retrieved sources. An item left citing nothing is
    dropped; so is an application that does not cite both a theory
    passage and an evidence passage, and a condition that rests only on
    theory. Returns the kept items and how many were dropped."""
    kept, dropped = [], 0
    for item in items:
        evidence = tuple(n for n in item.evidence if n in known)
        theory = [n for n in evidence if purposes.get(n) == THEORY_PURPOSE]
        facts = [n for n in evidence if purposes.get(n) != THEORY_PURPOSE]
        if (
            not evidence
            or (item.kind is AnalysisItemKind.APPLICATION and not (theory and facts))
            or (item.kind is AnalysisItemKind.CONDITION and not facts)
        ):
            dropped += 1
            continue
        kept.append(AnalysisItem(item.kind, item.text, evidence, item.label))
    return kept, dropped
