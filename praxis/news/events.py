"""Events: reports from one or more outlets about the same happening
(F01, F02; SD03's ``Event``).

An event holds its reports in a fixed order, so the summary can cite them
as [1], [2]. How sure the grouping is, and whether the model could
summarise the event, are part of the event: an event that rests on one
report, or whose grouping is doubtful, is shown as such (F01: "Events
with insufficient information or uncertain grouping should not be
presented as confidently established").
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from enum import Enum
from uuid import NAMESPACE_URL, UUID, uuid5

from praxis.documents import NewsArticle


class Grouping(Enum):
    SINGLE_REPORT = "single report"
    CONFIDENT = "grouped"
    UNCERTAIN = "grouping uncertain"


class SummaryStatus(Enum):
    NOT_SUMMARIZED = "not summarized"
    SUMMARIZED = "summarized"
    # The model failed or its summary could not be trusted: show the
    # headlines and sources instead (UC01, SD03's "fallback headline/source view").
    HEADLINES_ONLY = "headlines only"


EVENT_CATEGORIES = (
    "politics", "economy", "labour", "conflict", "diplomacy",
    "environment", "rights", "society", "other",
)


@dataclass(frozen=True)
class Event:
    reports: tuple[NewsArticle, ...]
    grouping: Grouping
    title: str = ""
    summary: str = ""
    categories: tuple[str, ...] = ()
    summary_status: SummaryStatus = SummaryStatus.NOT_SUMMARIZED
    note: str = ""  # why the grouping or summary is doubtful
    id: UUID = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.reports:
            raise ValueError("An event needs at least one report.")
        object.__setattr__(self, "reports", tuple(self.reports))
        object.__setattr__(self, "categories", tuple(self.categories))
        if self.id is None:
            object.__setattr__(self, "id", event_id(self.reports))

    @property
    def headline(self) -> str:
        """The model's title, or the newest report's headline."""
        return self.title or self.reports[0].title

    @property
    def outlets(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(r.outlet for r in self.reports))

    @property
    def first_date(self) -> date | None:
        dates = [r.publication_date for r in self.reports if r.publication_date]
        return min(dates) if dates else None

    @property
    def last_date(self) -> date | None:
        dates = [r.publication_date for r in self.reports if r.publication_date]
        return max(dates) if dates else None

    @property
    def is_summarized(self) -> bool:
        return self.summary_status is SummaryStatus.SUMMARIZED

    def with_summary(self, **fields) -> Event:
        return replace(self, **fields)


def event_id(reports: tuple[NewsArticle, ...]) -> UUID:
    """The same set of reports always gives the same id, so a stored
    summary can be reused while an event has not changed."""
    key = ",".join(sorted(str(r.id) for r in reports))
    return uuid5(NAMESPACE_URL, f"praxis:event:{key}")
