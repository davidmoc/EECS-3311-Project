"""Reading the model's comparison and checking it against the passages.

The model replies in a fixed line format (``COMPARISON_RULES`` in
``praxis.agent.prompts``). ``parse_comparison`` turns the reply into points;
lines in any other form are ignored. ``check_points`` then keeps only the
points the compared passages can support: a point that compares sources
must cite passages from at least two of them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from praxis.agent.corpus import CITATION_MARK, cited_numbers
from praxis.comparison.models import (
    DIFFERENCE_ASPECTS,
    Comparability,
    ComparisonPoint,
    PointKind,
)

# "difference: framing | ... [1, 3]", optionally bulleted, numbered or in bold.
_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])?\s*\**\s*([a-z]+)\s*\**\s*:\s*(.+?)\s*$", re.IGNORECASE)

# "[1] vs [3]": joined into "[1, 3]" so no stray "vs" is left in the text.
_JOINED_MARKS = re.compile(r"\]\s*(?:vs\.?|versus|and|&|/|,)\s*\[", re.IGNORECASE)

_SPACE_BEFORE_MARK = re.compile(r"\s+([,.;:])")
_EMPTY_BRACKETS = re.compile(r"\s*\(\s*[,;]?\s*\)")

# Points that say something about more than one source.
CROSS_SOURCE_KINDS = (PointKind.SIMILARITY, PointKind.DIFFERENCE, PointKind.DISAGREEMENT)


@dataclass(frozen=True)
class ParsedComparison:
    comparability: Comparability
    comparability_note: str
    points: tuple[ComparisonPoint, ...]
    uncertainties: tuple[str, ...]


def parse_comparison(text: str) -> ParsedComparison | None:
    """The comparison in ``text``, or None if no line is in the reply format."""
    comparability, note = Comparability.UNKNOWN, ""
    points: list[ComparisonPoint] = []
    uncertain: dict[str, None] = {}
    recognised = False

    for line in text.splitlines():
        match = _LINE.match(line)
        if not match:
            continue
        kind, rest = match.group(1).lower(), _JOINED_MARKS.sub(", ", match.group(2))
        evidence = tuple(cited_numbers(rest))
        # "the Manifesto stresses trade ([10])" would keep "()" once the
        # marks are gone, so emptied brackets go with them.
        unmarked = _EMPTY_BRACKETS.sub("", CITATION_MARK.sub("", rest))
        fields = [_clean(part) for part in unmarked.split("|")]
        fields = [f for f in fields if f]
        if not fields:
            continue

        if kind == "comparability":
            parsed = Comparability.parse(fields[0])
            if parsed is not None:
                recognised = True
                comparability, note = parsed, " | ".join(fields[1:])
        elif kind == "difference":
            recognised = True
            aspect = _aspect(fields[0])
            description = " | ".join(fields[1:] if aspect and len(fields) > 1 else fields)
            points.append(ComparisonPoint(PointKind.DIFFERENCE, description, evidence, aspect or ""))
        elif kind in ("similarity", "disagreement", "observation"):
            recognised = True
            points.append(ComparisonPoint(PointKind(kind), " | ".join(fields), evidence))
        elif kind == "uncertain":
            recognised = True
            uncertain.setdefault(" | ".join(fields), None)

    if not recognised:
        return None
    return ParsedComparison(comparability, note, tuple(points), tuple(uncertain))


def check_points(
    points: tuple[ComparisonPoint, ...], source_of_passage: dict[int, object]
) -> tuple[list[ComparisonPoint], int]:
    """The points the passages support, and how many were left out.

    ``source_of_passage`` maps each passage number to the source it came
    from. Citations of passages that were not compared are removed; a point
    left with no citation is dropped, and so is a similarity, difference or
    disagreement whose citations all come from one source.
    """
    kept: list[ComparisonPoint] = []
    dropped = 0
    for point in points:
        evidence = tuple(n for n in point.evidence if n in source_of_passage)
        sources = {source_of_passage[n] for n in evidence}
        needed = 2 if point.kind in CROSS_SOURCE_KINDS else 1
        if len(sources) < needed:
            dropped += 1
            continue
        kept.append(point.with_evidence(evidence))
    return kept, dropped


def _aspect(word: str) -> str | None:
    word = word.lower().split()[0] if word.split() else ""
    for aspect in DIFFERENCE_ASPECTS:
        if word.startswith(aspect[:6]):  # also "assumption", "terminological"
            return aspect
    if word.startswith("omit"):  # "omitted context"
        return "omission"
    return None


def _clean(text: str) -> str:
    """Quotation marks are kept: a description may end with a quoted word.
    Removing "[2]" from "searches [2], details" leaves "searches , details",
    so space before punctuation goes too."""
    return _SPACE_BEFORE_MARK.sub(r"\1", " ".join(text.split())).strip(" .;,*")
