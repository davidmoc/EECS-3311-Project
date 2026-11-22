"""CompareSourcesCommand: retrieve each chosen source (F10, SD06's
"loop [Retrieve each source] executeTool(source retrieval)").

It is a ``ResearchCommand``, so it runs against a ``ResearchContext`` and
every tool call is counted against the session's budget, like the other
research commands.
"""

from __future__ import annotations

from praxis.comparison.models import SourceSelection
from praxis.research.commands import CommandOutcome, ResearchCommand, ResearchContext
from praxis.research.session import ResearchError

SOURCE_RETRIEVAL = "source_retrieval"
# Passages taken from a source found by subject; named paragraphs are all kept.
PASSAGES_PER_SOURCE = 3
MAX_NAMED_PARAGRAPHS = 6
PURPOSE = "comparison"

NOTHING_ON_SUBJECT = "No passage of “{title}” matched {searched}, so it was left out of the comparison."
TOO_MANY_PARAGRAPHS = (
    "{count} paragraphs of “{title}” were named; only the first "
    f"{MAX_NAMED_PARAGRAPHS} ({{kept}}) were compared."
)
RETRIEVAL_FAILED = "A source could not be retrieved ({error}), so it was left out of the comparison."


class CompareSourcesCommand(ResearchCommand):
    def __init__(
        self,
        subject: str,
        selections: tuple[SourceSelection, ...],
        attempt: int = 1,
        keywords: tuple[str, ...] = (),
    ) -> None:
        """``keywords`` are searched with the subject: a text may name the
        subject in other words ("allotment farmers" for "the peasantry")."""
        super().__init__(subject, attempt)
        if not selections:
            raise ResearchError("Choose the sources to compare.")
        self.selections = tuple(selections)
        self.keywords = tuple(k for k in keywords if k.strip())

    @property
    def search_query(self) -> str:
        return ", ".join([self.query, *self.keywords])

    def describe(self) -> str:
        count = len(self.selections)
        return f"Compare {count} source{'s' if count != 1 else ''} on: {self.query}"

    def retry(self) -> CompareSourcesCommand:
        if not self.can_retry:
            raise ResearchError(f"'{self.describe()}' has no attempts left.")
        return CompareSourcesCommand(self.query, self.selections, self.attempt + 1, self.keywords)

    @property
    def key(self) -> tuple:
        return (type(self), self.query.casefold(), self.selections)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, CompareSourcesCommand)
            and (other.query, other.selections, other.attempt)
            == (self.query, self.selections, self.attempt)
        )

    def __hash__(self) -> int:
        return hash((type(self), self.query, self.selections, self.attempt))

    def execute(self, context: ResearchContext) -> CommandOutcome:
        """Add each source's passages to the corpus, in the order the
        sources were chosen. A source that yields nothing is reported on
        the session and skipped; the others are still retrieved."""
        new: list[int] = []
        for selection in self.selections:
            tool_input: dict = {"document_id": str(selection.document_id)}
            if selection.paragraphs:
                named = list(dict.fromkeys(selection.paragraphs))
                tool_input["paragraphs"] = named[:MAX_NAMED_PARAGRAPHS]
                tool_input["limit"] = MAX_NAMED_PARAGRAPHS
                if len(named) > MAX_NAMED_PARAGRAPHS:
                    context.session.add_warning(TOO_MANY_PARAGRAPHS.format(
                        title=selection.label, count=len(named),
                        kept=", ".join(f"¶{n}" for n in named[:MAX_NAMED_PARAGRAPHS]),
                    ))
            else:
                tool_input["query"] = self.search_query
                tool_input["limit"] = PASSAGES_PER_SOURCE
            result = context.run_tool(SOURCE_RETRIEVAL, tool_input)
            if not result.success:
                context.session.add_warning(RETRIEVAL_FAILED.format(error=result.error))
                continue
            if not result.items:
                context.session.add_warning(
                    NOTHING_ON_SUBJECT.format(title=selection.label, searched=f"“{self.search_query}”")
                )
                continue
            for match in result.items:
                before = len(context.corpus)
                source = context.corpus.add_passage(match.document, match.passage)
                if len(context.corpus) > before:
                    new.append(source.number)
                    context.purposes[source.number] = PURPOSE
        if not new:
            return CommandOutcome(False, error="no source yielded a passage")
        return CommandOutcome(True, tuple(new))

