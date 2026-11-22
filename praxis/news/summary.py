"""Event summaries (F01, SD03's ``NewsSummaryService.summarize``).

One model call per event writes a neutral title, a short summary citing
the reports as [n], and categories, and says whether the reports really
are about one event. A summary the reports cannot support is not shown:
the card falls back to the headlines and sources (UC01: "If an event
cannot be summarized reliably, the system can present the retrieved
headlines and sources without generating a definitive summary").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from praxis.agent.corpus import cited_numbers
from praxis.agent.prompts import PromptBuilder
from praxis.llm import LLMClient, LLMError
from praxis.news.events import EVENT_CATEGORIES, Event, Grouping, SummaryStatus

_LINE = re.compile(r"^\s*(?:[-*•])?\s*\**\s*(title|summary|category|categories|same event)\s*\**\s*:\s*(.*?)\s*$", re.IGNORECASE)

NO_SUMMARY_LINE = "The model's reply had no summary."
UNCITED_SUMMARY = "The summary cited none of the reports."
UNKNOWN_REPORTS = "The summary cited {labels}, which {verb} not among the reports."
SUMMARY_FAILED = "The summary could not be generated: {}"
NOT_ONE_EVENT = "The model judged that these reports are {extent} about one event{reason}."


@dataclass(frozen=True)
class SummaryOutcome:
    event: Event
    tokens_used: int = 0


class NewsSummaryService:
    def __init__(self, llm: LLMClient | None, prompts: PromptBuilder | None = None) -> None:
        self._llm = llm
        self._prompts = prompts or PromptBuilder()

    @property
    def available(self) -> bool:
        return self._llm is not None

    def summarize(self, event: Event) -> SummaryOutcome:
        """The event with its card filled in, or marked headlines-only with
        the reason in its note. Never raises for a model failure."""
        if self._llm is None:
            return SummaryOutcome(event.with_summary(
                summary_status=SummaryStatus.HEADLINES_ONLY,
                note="No language model is configured.",
            ))
        prompt = self._prompts.build_event_summary_prompt([
            (r.outlet, r.publication_date.isoformat() if r.publication_date else "undated", r.title, r.text)
            for r in event.reports
        ])
        try:
            response = self._llm.generate(prompt)
        except LLMError as exc:
            return SummaryOutcome(event.with_summary(
                summary_status=SummaryStatus.HEADLINES_ONLY, note=SUMMARY_FAILED.format(exc),
            ))
        return SummaryOutcome(read_summary(event, response.text), response.total_tokens)


def read_summary(event: Event, text: str) -> Event:
    """``event`` with the card in the model's reply, checked against its reports."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = _LINE.match(line)
        if match:
            key = match.group(1).lower().replace("categories", "category")
            fields.setdefault(key, match.group(2).strip())

    title = fields.get("title", "").strip(" \"'*")
    summary = fields.get("summary", "")
    categories = tuple(dict.fromkeys(
        word for word in (w.strip(" .").lower() for w in fields.get("category", "").split(","))
        if word in EVENT_CATEGORIES
    ))

    grouping, notes = event.grouping, []
    extent, _, reason = fields.get("same event", "yes").partition("|")
    extent = extent.strip(" *").lower()
    if extent.startswith(("no", "partly", "part")) and len(event.reports) > 1:
        grouping = Grouping.UNCERTAIN
        reason = reason.strip()
        notes.append(NOT_ONE_EVENT.format(
            extent="not all" if extent.startswith("no") else "only partly",
            reason=f": {reason}" if reason else "",
        ))

    cited = cited_numbers(summary)
    unknown = [n for n in cited if not 1 <= n <= len(event.reports)]
    problem = None
    if not summary:
        problem = NO_SUMMARY_LINE
    elif unknown:
        labels = ", ".join(f"[{n}]" for n in unknown)
        problem = UNKNOWN_REPORTS.format(labels=labels, verb="is" if len(unknown) == 1 else "are")
    elif not cited:
        problem = UNCITED_SUMMARY
    if problem:
        return event.with_summary(
            grouping=grouping, summary_status=SummaryStatus.HEADLINES_ONLY,
            note=" ".join([*notes, problem]), categories=categories,
        )
    return event.with_summary(
        grouping=grouping,
        title=title,
        summary=summary,
        categories=categories,
        summary_status=SummaryStatus.SUMMARIZED,
        note=" ".join(notes),
    )
