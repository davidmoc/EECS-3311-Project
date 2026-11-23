"""Leftist traditions compared on a topic (F12, UC12; Stage 1's
``IdeologicalContextService``).

The model names the traditions whose position on the topic differs
materially from Marxism, and which library authors represent each
(``find_relevant_traditions``). Each tradition's passages are retrieved,
its representatives' own words first; a tradition the library holds no
text of may still be described by others, and that is said. The model then
states each position, the conditions it developed in, where the traditions
disagree, and the Marxist assessment of the others, all citing the passages
(``explain_historical_context``). Each tradition's texts are offered for
reading (``recommend_representative_texts``).

UC12's alternatives: a tradition with no material in the library is left
out (F12: "include only perspectives for which relevant material can be
found"); when no other tradition differs materially, none is introduced
("does not introduce one merely to create artificial balance"); and a
tradition's own position is kept apart from the Marxist assessment of it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from praxis.agent.corpus import ResearchCorpus, Source, cited_numbers
from praxis.agent.prompts import MAX_TRADITIONS, PromptBuilder, reader_context
from praxis.documents import Document, NewsArticle
from praxis.llm import LLMClient, LLMError
from praxis.reader_model import ReaderProfile
from praxis.research.history import SuggestedReading, strip_citations, suggested_readings
from praxis.tools import ToolManager

if TYPE_CHECKING:
    from praxis.library import LibraryService

PASSAGE_SEARCH = "passage_search"
SOURCE_RETRIEVAL = "source_retrieval"
MARXISM = "Marxism"
SEARCH_LIMIT = 20
OWN_PASSAGES = 3  # a tradition's own passages kept
REPORTED_PASSAGES = 2  # passages by others about a tradition with no own text
REPRESENTATIVE_DOCUMENTS = 3  # texts searched one by one when the general search misses them
MAX_LINES_PER_KIND = 4

NO_LLM_ERROR = (
    "Comparing traditions needs a language model to say which traditions "
    "differ on the topic (set OPENAI_API_KEY)."
)
UNREADABLE_TRADITIONS = "The model's choice of traditions could not be read, so nothing was compared."
NO_OTHER_TRADITION = (
    "No other leftist tradition was judged to hold a materially different "
    "position on this topic, so none is introduced."
)
NO_MATERIAL = "No passage on this topic was found for {name}, so it is left out."
ONLY_ONE_PERSPECTIVE = (
    "Only one tradition has passages on this topic in the library, so there "
    "is nothing to compare."
)
DESCRIBED_BY_OTHERS = (
    "The library holds no text by a representative of {name}, so its position "
    "comes only from other authors' descriptions of it."
)
COMPARISON_UNREADABLE = "The model's comparison could not be read, so only the passages are shown."
NO_DISAGREEMENT = (
    "No disagreement between the traditions was supported by the passages, "
    "so none is shown."
)
UNCITED_LINES = (
    "{count} line{s} of the comparison did not cite the passages {they} needed "
    "and {were} left out."
)

_PERSPECTIVE_LINE = re.compile(
    r"^\s*(?:[-*•]|\d+[.)])?\s*\**perspective\**\s*:\s*(.+?)\s*$", re.IGNORECASE
)
_NONE_LINE = re.compile(r"^\s*(?:[-*•]\s*)?\**none\**\s*:\s*(.+?)\s*$", re.IGNORECASE)
_COMPARISON_LINE = re.compile(
    r"^\s*(?:[-*•]|\d+[.)])?\s*\**(position|conditions|disagreement|assessment|gap)\**\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)


class TraditionsError(Exception):
    """The request could not be served (for example, no model)."""


@dataclass(frozen=True)
class Tradition:
    """A tradition the model judged relevant, as it named it."""

    name: str
    representatives: tuple[str, ...] = ()
    keywords: str = ""
    relevance: str = ""

    @property
    def is_marxism(self) -> bool:
        return self.name.casefold().startswith("marxis")


@dataclass(frozen=True)
class ParsedTraditions:
    traditions: tuple[Tradition, ...]
    none_reason: str = ""


class StatementKind(Enum):
    POSITION = "position"
    CONDITIONS = "conditions"
    ASSESSMENT = "assessment"


@dataclass(frozen=True)
class Statement:
    """A line about one tradition."""

    kind: StatementKind
    tradition: str
    text: str
    evidence: tuple[int, ...]
    # For a position: whether it cites the tradition's own words.
    in_own_words: bool = True


@dataclass(frozen=True)
class Disagreement:
    text: str
    evidence: tuple[int, ...]
    sides: str = ""  # "Leninism vs Anarchism", when the model names them


@dataclass(frozen=True)
class Perspective:
    """A tradition with the passages found for it."""

    tradition: Tradition
    own: tuple[int, ...] = ()  # passage numbers by its representatives
    reported: tuple[int, ...] = ()  # passages by others about it
    readings: tuple[SuggestedReading, ...] = ()

    @property
    def name(self) -> str:
        return self.tradition.name

    @property
    def numbers(self) -> tuple[int, ...]:
        return self.own + self.reported

    @property
    def in_own_words(self) -> bool:
        return bool(self.own)


class TraditionsStatus(Enum):
    COMPARED = "compared"
    NO_OTHER_TRADITION = "no other tradition"
    ONE_PERSPECTIVE = "one perspective"  # others named, but no material found
    NOT_COMPARED = "not compared"  # passages found, no usable comparison


@dataclass(frozen=True)
class TraditionsComparison:
    topic: str
    status: TraditionsStatus
    perspectives: tuple[Perspective, ...] = ()
    sources: tuple[Source, ...] = ()
    statements: tuple[Statement, ...] = ()
    disagreements: tuple[Disagreement, ...] = ()
    gaps: tuple[str, ...] = ()
    none_reason: str = ""
    left_out: tuple[str, ...] = ()  # traditions named but with no material
    research_session: str | None = None
    personalized: bool = False
    warnings: tuple[str, ...] = ()
    tokens_used: int = 0

    def statements_of(self, tradition: str, kind: StatementKind) -> list[Statement]:
        return [s for s in self.statements if s.tradition == tradition and s.kind is kind]

    def perspective_of(self, number: int) -> Perspective | None:
        return next((p for p in self.perspectives if number in p.numbers), None)

    @property
    def cited(self) -> tuple[Source, ...]:
        numbers = {n for s in self.statements for n in s.evidence}
        numbers |= {n for d in self.disagreements for n in d.evidence}
        return tuple(s for s in self.sources if s.number in numbers)


@dataclass(frozen=True)
class ParsedTraditionComparison:
    statements: tuple[Statement, ...]
    disagreements: tuple[Disagreement, ...]
    gaps: tuple[str, ...]


def parse_traditions(text: str) -> ParsedTraditions | None:
    """The traditions the model named, Marxism first, each once, or None
    if no line is in the reply format. An author named for two traditions
    stays with the first."""
    traditions: dict[str, Tradition] = {}
    claimed: set[str] = set()
    none_reason = ""
    readable = False
    for line in text.splitlines():
        if match := _NONE_LINE.match(line):
            readable = True
            none_reason = none_reason or match[1].strip()
            continue
        match = _PERSPECTIVE_LINE.match(line)
        if not match:
            continue
        fields = [part.strip(" *\"'") for part in match[1].split("|")]
        name = fields[0]
        if not name or name.casefold() in traditions:
            continue
        readable = True
        representatives = []
        for author in (fields[1] if len(fields) > 1 else "").split(","):
            author = author.strip(" *\"'.")
            if author and author.casefold() not in ("none", "n/a", "-") and author.casefold() not in claimed:
                claimed.add(author.casefold())
                representatives.append(author)
        traditions[name.casefold()] = Tradition(
            name,
            tuple(representatives),
            fields[2] if len(fields) > 2 else "",
            " | ".join(fields[3:]) if len(fields) > 3 else "",
        )
    if not readable:
        return None
    ordered = sorted(traditions.values(), key=lambda t: not t.is_marxism)
    return ParsedTraditions(tuple(ordered[:MAX_TRADITIONS]), none_reason)


def parse_tradition_comparison(text: str) -> ParsedTraditionComparison | None:
    """The comparison's lines, or None if no line is in the reply format.
    Each kind keeps at most ``MAX_LINES_PER_KIND`` lines."""
    statements: list[Statement] = []
    disagreements: list[Disagreement] = []
    gaps: list[str] = []
    counts: dict[str, int] = {}
    readable = False
    for line in text.splitlines():
        match = _COMPARISON_LINE.match(line)
        if not match:
            continue
        readable = True
        kind, body = match[1].lower(), match[2]
        if counts.get(kind, 0) >= MAX_LINES_PER_KIND:
            continue
        counts[kind] = counts.get(kind, 0) + 1
        evidence = tuple(cited_numbers(body))
        clean = strip_citations(body)
        if kind == "gap":
            gaps.append(clean)
        elif kind == "disagreement":
            # The format gives no head, but the model sometimes names the
            # sides first ("Leninism vs Anarchism | ..."); keep them apart.
            head, bar, rest = clean.partition("|")
            if bar and rest.strip():
                disagreements.append(Disagreement(rest.strip(), evidence, head.strip(" *")))
            else:
                disagreements.append(Disagreement(clean, evidence))
        else:
            head, bar, rest = clean.partition("|")
            if not bar or not rest.strip():
                continue  # a statement must say which tradition it is about
            statements.append(Statement(StatementKind(kind), head.strip(" *"), rest.strip(), evidence))
    if not readable:
        return None
    return ParsedTraditionComparison(tuple(statements), tuple(disagreements), tuple(gaps))


def check_comparison(
    parsed: ParsedTraditionComparison, perspectives: tuple[Perspective, ...]
) -> tuple[list[Statement], list[Disagreement], int]:
    """The lines the passages support, and how many were left out.

    A statement must name one of the perspectives and cite at least one
    of that perspective's passages; a position citing none of its own
    passages is marked as others' description. A disagreement must cite
    passages of at least two perspectives. An assessment of Marxism itself
    is dropped: the assessment is the Marxist view of the others.
    """
    known = {n for p in perspectives for n in p.numbers}
    statements: list[Statement] = []
    disagreements: list[Disagreement] = []
    dropped = 0
    for statement in parsed.statements:
        perspective = _match_perspective(statement.tradition, perspectives)
        evidence = tuple(n for n in statement.evidence if n in known)
        if (
            perspective is None
            or not evidence
            or (statement.kind is StatementKind.ASSESSMENT and perspective.tradition.is_marxism)
        ):
            dropped += 1
            continue
        own_words = any(n in perspective.own for n in evidence)
        statements.append(Statement(statement.kind, perspective.name, statement.text, evidence, own_words))
    for disagreement in parsed.disagreements:
        evidence = tuple(n for n in disagreement.evidence if n in known)
        sides = {p.name for p in perspectives if any(n in p.numbers for n in evidence)}
        if len(sides) < 2:
            dropped += 1
            continue
        disagreements.append(Disagreement(disagreement.text, evidence, disagreement.sides))
    return statements, disagreements, dropped


def _match_perspective(name: str, perspectives: tuple[Perspective, ...]) -> Perspective | None:
    """The perspective ``name`` refers to: by exact name, or one name
    starting with the other ("Anarchism" for "Anarchism (anarcho-communism)")."""
    wanted = name.casefold().strip()
    for perspective in perspectives:
        if perspective.name.casefold() == wanted:
            return perspective
    for perspective in perspectives:
        have = perspective.name.casefold()
        if wanted and (have.startswith(wanted) or wanted.startswith(have)):
            return perspective
    return None


def authored_by(document: Document, representative: str) -> bool:
    """Whether ``representative`` is among the document's authors, matched
    on their surname: "Peter Kropotkin" or "Kropotkin" for "Peter Kropotkin",
    "Marx" for "Karl Marx and Friedrich Engels"."""
    surname = representative.split()[-1].casefold() if representative.split() else ""
    if len(surname) < 3:
        return False
    return re.search(rf"\b{re.escape(surname)}\b", document.author.casefold()) is not None


class IdeologicalContextService:
    """F12. Needs the ``passage_search`` and ``source_retrieval`` tools."""

    def __init__(
        self,
        tools: ToolManager,
        library: LibraryService,
        llm: LLMClient | None = None,
        prompts: PromptBuilder | None = None,
    ) -> None:
        self._tools = tools
        self._library = library
        self._llm = llm
        self._prompts = prompts or PromptBuilder()

    def compare_traditions(
        self,
        topic: str,
        profile: ReaderProfile | None = None,
        research_session: str | None = None,
    ) -> TraditionsComparison:
        """How Marxism and the traditions that differ from it treat
        ``topic``, from library passages."""
        topic = " ".join(topic.split())
        if not topic:
            raise TraditionsError("Name a topic or question to compare traditions on.")
        if self._llm is None:
            raise TraditionsError(NO_LLM_ERROR)
        tokens = 0
        warnings: list[str] = []

        def result(status: TraditionsStatus, **fields) -> TraditionsComparison:
            return TraditionsComparison(
                topic, status, research_session=research_session,
                warnings=tuple(warnings), tokens_used=tokens, **fields,
            )

        documents = [d for d in self._library.browse() if d.kind != NewsArticle.kind]
        parsed, tokens = self.find_relevant_traditions(topic, documents)
        traditions = list(parsed.traditions)
        if not any(t.is_marxism for t in traditions):
            traditions.insert(0, Tradition(MARXISM, keywords=topic))

        corpus = ResearchCorpus()
        perspectives, left_out = self._retrieve(topic, traditions, documents, corpus, warnings)
        others = [p for p in perspectives if not p.tradition.is_marxism]
        sources = tuple(corpus.sources)
        if len(traditions) == 1:
            warnings.insert(0, NO_OTHER_TRADITION)
            return result(
                TraditionsStatus.NO_OTHER_TRADITION, perspectives=tuple(perspectives),
                sources=sources, none_reason=parsed.none_reason,
            )
        if len(perspectives) < 2 or not others:
            warnings.append(ONLY_ONE_PERSPECTIVE)
            return result(
                TraditionsStatus.ONE_PERSPECTIVE, perspectives=tuple(perspectives),
                sources=sources, left_out=tuple(left_out),
            )
        for perspective in perspectives:
            if not perspective.in_own_words:
                warnings.append(DESCRIBED_BY_OTHERS.format(name=perspective.name))

        groups = [
            (p.name, [corpus.source(n) for n in p.own], [corpus.source(n) for n in p.reported])
            for p in perspectives
        ]
        prompt = self._prompts.build_tradition_comparison_prompt(topic, groups, profile)
        try:
            response = self._llm.generate(prompt)
        except LLMError as exc:
            warnings.append(f"The comparison could not be generated: {exc}")
            return result(
                TraditionsStatus.NOT_COMPARED,
                perspectives=self.recommend_representative_texts(perspectives, corpus, set()),
                sources=sources, left_out=tuple(left_out),
            )
        tokens += response.total_tokens
        comparison = parse_tradition_comparison(response.text)
        if comparison is None:
            warnings.append(COMPARISON_UNREADABLE)
            return result(
                TraditionsStatus.NOT_COMPARED,
                perspectives=self.recommend_representative_texts(perspectives, corpus, set()),
                sources=sources, left_out=tuple(left_out),
            )
        statements, disagreements, dropped = check_comparison(comparison, tuple(perspectives))
        if dropped:
            warnings.append(UNCITED_LINES.format(
                count=dropped, s="s" if dropped != 1 else "",
                they="they" if dropped != 1 else "it", were="were" if dropped != 1 else "was",
            ))
        if not disagreements:
            warnings.append(NO_DISAGREEMENT)
        cited = {n for s in statements for n in s.evidence} | {n for d in disagreements for n in d.evidence}
        return result(
            TraditionsStatus.COMPARED if statements else TraditionsStatus.NOT_COMPARED,
            perspectives=self.recommend_representative_texts(perspectives, corpus, cited),
            sources=sources,
            statements=tuple(statements),
            disagreements=tuple(disagreements),
            gaps=comparison.gaps,
            left_out=tuple(left_out),
            personalized=reader_context(profile) is not None,
        )

    def find_relevant_traditions(
        self, topic: str, documents: list[Document]
    ) -> tuple[ParsedTraditions, int]:
        """The traditions the model judges to differ on ``topic``, with
        their representatives among the library's authors, and the tokens
        spent asking."""
        try:
            response = self._llm.generate(
                self._prompts.build_tradition_prompt(topic, _authors(documents))
            )
        except LLMError as exc:
            raise TraditionsError(f"The model could not be asked which traditions differ: {exc}") from exc
        parsed = parse_traditions(response.text)
        if parsed is None:
            raise TraditionsError(UNREADABLE_TRADITIONS)
        return parsed, response.total_tokens

    def recommend_representative_texts(
        self, perspectives: list[Perspective], corpus: ResearchCorpus, cited: set[int]
    ) -> tuple[Perspective, ...]:
        """Each perspective with the texts to read for it: its own
        representatives' texts, the cited ones first. A tradition known
        only from others' descriptions gets no reading."""
        with_readings = []
        for perspective in perspectives:
            own = [corpus.source(n) for n in perspective.own]
            ranked = [s for s in own if s.number in cited] + [s for s in own if s.number not in cited]
            with_readings.append(Perspective(
                perspective.tradition, perspective.own, perspective.reported,
                suggested_readings(tuple(ranked)),
            ))
        return tuple(with_readings)

    def _retrieve(
        self,
        topic: str,
        traditions: list[Tradition],
        documents: list[Document],
        corpus: ResearchCorpus,
        warnings: list[str],
    ) -> tuple[list[Perspective], list[str]]:
        """Each tradition's passages: its representatives' own first; if
        none, others' passages about it. Traditions with neither are left
        out. Each document belongs to the first tradition claiming it."""
        owner: dict[UUID, str] = {}
        for tradition in traditions:
            for document in documents:
                if document.id not in owner and any(
                    authored_by(document, r) for r in tradition.representatives
                ):
                    owner[document.id] = tradition.name
        perspectives: list[Perspective] = []
        left_out: list[str] = []
        for tradition in traditions:
            query = " ".join(f"{topic} {tradition.keywords}".split())
            matches = self._search(query, warnings)
            own_matches = [m for m in matches if owner.get(m.document.id) == tradition.name]
            if not own_matches:
                for document in [d for d in documents if owner.get(d.id) == tradition.name][:REPRESENTATIVE_DOCUMENTS]:
                    own_matches.extend(self._search_in(document, query, warnings))
            own = self._add(own_matches, corpus, OWN_PASSAGES)
            reported: list[int] = []
            if not own:
                about = self._search(f"{tradition.name} {tradition.keywords}", warnings)
                reported = self._add(
                    [m for m in about if owner.get(m.document.id) != tradition.name],
                    corpus, REPORTED_PASSAGES,
                )
            if not own and not reported:
                warnings.append(NO_MATERIAL.format(name=tradition.name))
                left_out.append(tradition.name)
                continue
            perspectives.append(Perspective(tradition, tuple(own), tuple(reported)))
        return perspectives, left_out

    def _search(self, query: str, warnings: list[str]) -> list:
        result = self._tools.execute_tool(PASSAGE_SEARCH, {"query": query, "limit": SEARCH_LIMIT})
        if not result.success:
            warnings.append(f"Library search failed: {result.error}")
            return []
        return [m for m in result.items if m.document.kind != NewsArticle.kind]

    def _search_in(self, document: Document, query: str, warnings: list[str]) -> list:
        result = self._tools.execute_tool(
            SOURCE_RETRIEVAL, {"document_id": str(document.id), "query": query, "limit": OWN_PASSAGES}
        )
        if not result.success:
            warnings.append(f"Searching “{document.title}” failed: {result.error}")
            return []
        return list(result.items)

    @staticmethod
    def _add(matches: list, corpus: ResearchCorpus, limit: int) -> list[int]:
        """Add up to ``limit`` passages not already in the corpus: a
        passage belongs to one tradition only."""
        numbers: list[int] = []
        for match in matches:
            if len(numbers) >= limit:
                break
            before = len(corpus)
            source = corpus.add_passage(match.document, match.passage)
            if len(corpus) > before:
                numbers.append(source.number)
        return numbers


def _authors(documents: list[Document]) -> list[tuple[str, list[str]]]:
    """Each author with their titles, in library order."""
    by_author: dict[str, list[str]] = {}
    for document in documents:
        by_author.setdefault(document.author, []).append(document.title)
    return list(by_author.items())
