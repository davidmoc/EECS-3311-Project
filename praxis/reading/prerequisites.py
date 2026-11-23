"""Prerequisite-guided learning (F08, UC08, SD05's ``buildLearningPath``).

``PrerequisiteService.build_learning_path`` asks the model what a target
topic or text assumes, removes what the reader is known to understand,
finds library passages for each remaining prerequisite, and returns an
ordered ``LearningPath``. A prerequisite the library has nothing on keeps
the model's short orientation and is reported as a gap (UC08: "If no
appropriate reading exists, the system may provide a basic orientation and
identify the gap").

With a ``SourceDiscoveryService``, texts on the target and each
prerequisite are first found beyond the library and added to it, so a
path on a current event or a country is not limited to the classics the
library already holds. A step's readings come first from the texts found
for that step, then from the rest of the library.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from praxis.agent.prompts import MAX_PREREQUISITES, PREREQUISITE_KINDS, PromptBuilder
from praxis.documents import Citation, Document, NewsArticle
from praxis.llm import LLMClient, LLMError
from praxis.reader_model import KnowledgeArea, KnowledgeLevel, ReaderProfile, normalize_topic
from praxis.tools import ToolManager

if TYPE_CHECKING:  # praxis.persistence.learning_paths imports this module
    from praxis.discovery import SourceDiscoveryService
    from praxis.persistence.learning_paths import LearningPathRepository, LearningPathSummary

PASSAGE_SEARCH = "passage_search"
SOURCE_RETRIEVAL = "source_retrieval"
READINGS_PER_STEP = 2
SEARCH_LIMIT = 8
# Passages searched within each text found for a step.
FOUND_TEXT_PASSAGES = 2

NO_LLM_ERROR = (
    "No language model is configured (set OPENAI_API_KEY), so prerequisites "
    "cannot be identified."
)
UNREADABLE_ERROR = "The model's list of prerequisites could not be read; try again."
SPARSE_PROFILE_WARNING = (
    "Little is known about what you already understand, so every step is a "
    "suggestion. Skip what you know, or record it with praxis profile know."
)
NOT_STORED_WARNING = "The learning path could not be stored, so its progress cannot be kept: {}"
PERSONALIZATION_OFF_WARNING = (
    "Personalization is off, so your knowledge was not consulted and every "
    "step is a suggestion."
)

_PREREQUISITE_LINE = re.compile(
    r"^\s*(?:[-*•]|\d+[.)])?\s*prerequisite\s*:\s*([^|]+?)\s*(?:\|\s*([^|]*?)\s*)?(?:\|\s*([^|]*?)\s*)?$",
    re.IGNORECASE,
)
_FIELD_LINE = re.compile(r"^\s*(?:[-*•]\s*)?(search|why|orientation)\s*:\s*(.*?)\s*$", re.IGNORECASE)


class PrerequisiteError(Exception):
    """No learning path could be built; the message says why."""


class StepStatus(Enum):
    TODO = "to do"
    DONE = "done"
    KNOWN = "already known"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class Prerequisite:
    """What the model says a target assumes (SD05's "prerequisite topics")."""

    name: str
    kind: str = "concept"
    essential: bool = True
    search: str = ""
    why: str = ""
    orientation: str = ""


@dataclass
class LearningStep:
    """One step of a path: a prerequisite and where to learn it.

    ``required`` is False when the step is only a suggestion (UC08: "If
    the system lacks confidence in a knowledge assessment, it presents the
    prerequisite as a suggestion rather than a requirement"). ``readings``
    are library passages; when there are none, ``orientation`` is all the
    path offers and the step is a gap.
    """

    prerequisite: Prerequisite
    readings: tuple[Citation, ...] = ()
    required: bool = False
    # Why it is only a suggestion, if the reader may already know it.
    note: str = ""
    status: StepStatus = StepStatus.TODO

    @property
    def name(self) -> str:
        return self.prerequisite.name

    @property
    def is_gap(self) -> bool:
        return not self.readings


@dataclass
class LearningPath:
    target: str
    steps: list[LearningStep] = field(default_factory=list)
    # Prerequisites left out because the reader said they know them.
    already_known: tuple[str, ...] = ()
    personalized: bool = False
    target_document_id: UUID | None = None
    warnings: tuple[str, ...] = ()
    tokens_used: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: UUID = field(default_factory=uuid4)

    @property
    def no_path_required(self) -> bool:
        """SD05's "user already knows prerequisites" branch."""
        return not self.steps and bool(self.already_known)

    @property
    def gaps(self) -> list[LearningStep]:
        return [step for step in self.steps if step.is_gap]

    @property
    def settled_count(self) -> int:
        """Steps the reader has dealt with: done, already known or skipped."""
        return sum(step.status is not StepStatus.TODO for step in self.steps)

    @property
    def next_step(self) -> tuple[int, LearningStep] | None:
        """The first step still to do, with its 1-based number."""
        return next(
            ((n, s) for n, s in enumerate(self.steps, start=1) if s.status is StepStatus.TODO),
            None,
        )


def parse_prerequisites(text: str) -> list[Prerequisite]:
    """The model's prerequisites in order, each name once, at most
    ``MAX_PREREQUISITES``. Field lines attach to the prerequisite above
    them; an unknown kind becomes "concept", and anything but "helpful"
    counts as essential."""
    found: list[dict] = []
    for line in text.splitlines():
        if match := _PREREQUISITE_LINE.match(line):
            kind = (match[2] or "").lower()
            found.append({
                "name": match[1].strip(" *\"'"),
                "kind": kind if kind in PREREQUISITE_KINDS else "concept",
                "essential": (match[3] or "").lower() != "helpful",
            })
        elif found and (match := _FIELD_LINE.match(line)):
            found[-1].setdefault(match[1].lower(), match[2])
    unique: dict[str, Prerequisite] = {}
    for fields in found:
        if not fields["name"]:
            continue
        unique.setdefault(normalize_topic(fields["name"]), Prerequisite(**fields))
    return list(unique.values())[:MAX_PREREQUISITES]


class PrerequisiteService:
    def __init__(
        self,
        tools: ToolManager,
        llm: LLMClient | None = None,
        prompts: PromptBuilder | None = None,
        repository: LearningPathRepository | None = None,
        discovery: SourceDiscoveryService | None = None,
    ) -> None:
        """Without ``repository``, paths are built but not stored; without
        ``discovery``, readings come only from the library as it is."""
        self._tools = tools
        self._llm = llm
        self._prompts = prompts or PromptBuilder()
        self._repository = repository
        self._discovery = discovery

    # --- stored paths and progress (UC08 steps 7-8) -----------------------

    def get_path(self, path_id: UUID) -> LearningPath:
        path = self._require_repository().get(path_id)
        if path is None:
            raise PrerequisiteError(f"There is no learning path {path_id}.")
        return path

    def list_paths(self, limit: int = 20) -> list[LearningPathSummary]:
        return self._require_repository().list_recent(limit)

    def find_path(self, id_prefix: str) -> UUID:
        prefix = id_prefix.strip().lower()
        if not prefix:
            raise PrerequisiteError("A learning path id is required.")
        matches = self._require_repository().find_ids(prefix)
        if not matches:
            raise PrerequisiteError(f"No learning path with id starting '{prefix}'.")
        if len(matches) > 1:
            raise PrerequisiteError(f"Id '{prefix}' matches {len(matches)} paths; use more characters.")
        return matches[0]

    def set_step_status(self, path_id: UUID, number: int, status: StepStatus) -> LearningPath:
        """Record that step ``number`` (1-based) is done, already known,
        skipped, or back to do. Updating the reader model is left to the
        caller, which publishes the activity (Observer, as for reading)."""
        path = self.get_path(path_id)
        if not 1 <= number <= len(path.steps):
            raise PrerequisiteError(
                f"This path has {len(path.steps)} step{'s' if len(path.steps) != 1 else ''}; there is no step {number}."
            )
        path.steps[number - 1].status = status
        self._require_repository().save(path)
        return path

    def _require_repository(self) -> LearningPathRepository:
        if self._repository is None:
            raise PrerequisiteError("Learning paths are not being stored.")
        return self._repository

    # --- building a path (SD05) -------------------------------------------

    def identify_prerequisites(
        self, target: str, known_topics: list[str] = ()
    ) -> tuple[list[Prerequisite], int]:
        """What ``target`` assumes, in learning order, and the tokens used.
        Raises ``PrerequisiteError`` without a model, on failure, or for a
        reply in another form."""
        if self._llm is None:
            raise PrerequisiteError(NO_LLM_ERROR)
        prompt = self._prompts.build_prerequisite_prompt(target, list(known_topics))
        try:
            response = self._llm.generate(prompt)
        except LLMError as exc:
            raise PrerequisiteError(f"Prerequisites could not be identified: {exc}") from exc
        prerequisites = parse_prerequisites(response.text)
        if not prerequisites:
            raise PrerequisiteError(UNREADABLE_ERROR)
        return prerequisites, response.total_tokens

    def build_learning_path(
        self,
        target: str,
        profile: ReaderProfile | None = None,
        document: Document | None = None,
    ) -> LearningPath:
        """An ordered path of what the reader still needs for ``target``.

        With ``document``, the target is that text: it is described to
        the model, and its own passages are not offered as readings.
        """
        target = " ".join(target.split())
        if document is not None:
            target = target or describe_text(document)
        if not target:
            raise PrerequisiteError("Name a topic or text to build a learning path for.")

        uses_profile = profile is not None and profile.personalization_enabled
        warnings: list[str] = []
        if profile is not None and not profile.personalization_enabled:
            warnings.append(PERSONALIZATION_OFF_WARNING)
        # Interests and reading history say nothing about what the reader
        # understands; only knowledge areas do.
        assessed = uses_profile and bool(profile.knowledge.areas)
        if profile is None or (uses_profile and not assessed):
            warnings.append(SPARSE_PROFILE_WARNING)
        known_topics = sorted(profile.knowledge.areas) if uses_profile else []

        prerequisites, tokens = self.identify_prerequisites(target, known_topics)
        found: dict[str, list[Document]] = {}  # prerequisite name -> texts found for it
        if self._discovery is not None:
            report = self._discovery.discover(target, [p.name for p in prerequisites])
            tokens += report.tokens_used
            if note := report.note():
                warnings.append(note)
            for found_document in report.documents:
                for topic in found_document.topics:
                    found.setdefault(topic.lower(), []).append(found_document)

        steps: list[LearningStep] = []
        already_known: list[str] = []
        offered: set[tuple[UUID, str]] = set()  # passages earlier steps already offer
        for prerequisite in prerequisites:
            step = LearningStep(prerequisite, required=assessed and prerequisite.essential)
            if uses_profile:
                area = known_area(profile, prerequisite.name)
                if area is not None and area.level >= KnowledgeLevel.INTRODUCTORY:
                    if not area.is_inferred:
                        already_known.append(prerequisite.name)
                        continue
                    # Known only by inference from reading: suggest, do not require.
                    step.required = False
                    step.note = (
                        f"You may already know this: your reading suggests "
                        f"{area.level.name.lower()} level."
                    )
            step.readings = self._find_readings(
                prerequisite, document, offered, warnings, found.get(prerequisite.name.lower(), [])
            )
            offered.update((c.document_id, c.locator) for c in step.readings)
            steps.append(step)

        gaps = [step.name for step in steps if step.is_gap]
        if gaps:
            warnings.append(
                "The library has nothing on " + ", ".join(gaps)
                + "; only a short AI orientation is given for "
                + ("it." if len(gaps) == 1 else "them.")
            )
        path = LearningPath(
            target,
            steps,
            tuple(already_known),
            personalized=bool(known_topics),
            target_document_id=document.id if document is not None else None,
            warnings=tuple(warnings),
            tokens_used=tokens,
        )
        if self._repository is not None and path.steps:
            try:
                self._repository.save(path)
            except sqlite3.Error as exc:
                path.warnings = (*path.warnings, NOT_STORED_WARNING.format(exc))
        return path

    def _find_readings(
        self,
        prerequisite: Prerequisite,
        target: Document | None,
        offered: set[tuple[UUID, str]],
        warnings: list[str],
        found: list[Document] = (),
    ) -> tuple[Citation, ...]:
        """Up to ``READINGS_PER_STEP`` passages, from different texts where
        possible, never from the target text or the news, and none that an
        earlier step already offers. Passages of ``found`` (texts found on
        the web for this step) come first."""
        query = f"{prerequisite.name} {prerequisite.search}".strip()
        candidates = []
        for found_document in found:
            result = self._tools.execute_tool(SOURCE_RETRIEVAL, {
                "document_id": str(found_document.id), "query": query, "limit": FOUND_TEXT_PASSAGES,
            })
            if result.success:
                candidates.extend(result.items)
        result = self._tools.execute_tool(PASSAGE_SEARCH, {"query": query, "limit": SEARCH_LIMIT})
        if not result.success:
            warnings.append(f"Library search for {prerequisite.name} failed: {result.error}")
            if not candidates:
                return ()
        else:
            candidates.extend(result.items)
        usable, keys = [], set(offered)
        for match in candidates:
            key = (match.document.id, match.passage.locator)
            if match.document.kind == NewsArticle.kind or key in keys:
                continue
            if target is not None and match.document.id == target.id:
                continue
            keys.add(key)
            usable.append(match)
        # One passage per text first, then fill with the best remaining.
        chosen, seen = [], set()
        for match in usable:
            if match.document.id not in seen and len(chosen) < READINGS_PER_STEP:
                chosen.append(match)
                seen.add(match.document.id)
        for match in usable:
            if len(chosen) >= READINGS_PER_STEP:
                break
            if match not in chosen:
                chosen.append(match)
        return tuple(match.document.cite(match.passage) for match in chosen)


_LEADING_ARTICLE = re.compile(r"^(?:the|a|an)\s+")


def topic_key(name: str) -> str:
    """A topic name for matching: normalized, without a leading article,
    so "The labour theory of value" matches "labour theory of value"."""
    return _LEADING_ARTICLE.sub("", normalize_topic(name))


def known_area(profile: ReaderProfile, name: str) -> KnowledgeArea | None:
    """The reader's knowledge area for ``name``, matched by ``topic_key``."""
    wanted = topic_key(name)
    return next(
        (area for key, area in profile.knowledge.areas.items() if topic_key(key) == wanted),
        None,
    )


def describe_text(document: Document) -> str:
    """How a target text is named to the model. Its catalogue topics are
    left out: given them, the model listed what the text teaches (for the
    Brumaire, "historical materialism") as what it assumes."""
    year = f" ({document.publication_date.year})" if document.publication_date else ""
    return f"the text “{document.title}”{year} by {document.author}"
