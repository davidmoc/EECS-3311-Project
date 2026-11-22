"""Source and framing comparison (F10, UC10, SD06)."""

from praxis.comparison.analysis import ParsedComparison, check_points, parse_comparison
from praxis.comparison.models import (
    DIFFERENCE_ASPECTS,
    Comparability,
    ComparisonPoint,
    PointKind,
    SourceComparison,
    SourceProfile,
    SourceSelection,
)

__all__ = [
    "DIFFERENCE_ASPECTS",
    "Comparability",
    "ComparisonPoint",
    "ParsedComparison",
    "PointKind",
    "SourceComparison",
    "SourceProfile",
    "SourceSelection",
    "check_points",
    "parse_comparison",
]
