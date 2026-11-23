"""Prerequisite-guided learning (F08, UC08, SD05's ``buildLearningPath``).

``PrerequisiteService.build_learning_path`` asks the model what a target
topic or text assumes, removes what the reader is known to understand,
finds library passages for each remaining prerequisite, and returns an
ordered ``LearningPath``. A prerequisite the library has nothing on keeps
the model's short orientation and is reported as a gap (UC08: "If no
appropriate reading exists, the system may provide a basic orientation and
identify the gap").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from praxis.agent.prompts import MAX_PREREQUISITES, PREREQUISITE_KINDS, PromptBuilder
from praxis.documents import Citation, Document, NewsArticle
from praxis.llm import LLMClient, LLMError
from praxis.reader_model import KnowledgeLevel, ReaderProfile, normalize_topic
from praxis.tools import ToolManager

PASSAGE_SEARCH = "passage_search"
READINGS_PER_STEP = 2
SEARCH_LIMIT = 8
# Catalogue topics of a target text named to the model.
TARGET_TOPICS_SHOWN = 6

NO_LLM_ERROR = (
    "No language model is configured (set OPENAI_API_KEY), so prerequisites "
    "cannot be identified."
)
UNREADABLE_ERROR = "The model's list of prerequisites could not be read; try again."
SPARSE_PROFILE_WARNING = (
    "Little is known about what you already understand, so every step is a "
    "suggestion. Skip what you know, or record it with praxis profile know."
)
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
    ) -> None:
        self._tools = tools
        self._llm = llm
        self._prompts = prompts or PromptBuilder()

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
        elif profile is None or profile.is_sparse:
            warnings.append(SPARSE_PROFILE_WARNING)
        assessed = uses_profile and not profile.is_sparse
        known_topics = sorted(profile.knowledge.areas) if uses_profile else []

        prerequisites, tokens = self.identify_prerequisites(target, known_topics)

        steps: list[LearningStep] = []
        already_known: list[str] = []
        for prerequisite in prerequisites:
            step = LearningStep(prerequisite, required=assessed and prerequisite.essential)
            if uses_profile:
                area = profile.knowledge.areas.get(normalize_topic(prerequisite.name))
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
            step.readings = self._find_readings(prerequisite, document, warnings)
            steps.append(step)

        gaps = [step.name for step in steps if step.is_gap]
        if gaps:
            warnings.append(
                "The library has nothing on " + ", ".join(gaps)
                + "; only a short AI orientation is given for "
                + ("it." if len(gaps) == 1 else "them.")
            )
        return LearningPath(
            target,
            steps,
            tuple(already_known),
            personalized=bool(known_topics),
            target_document_id=document.id if document is not None else None,
            warnings=tuple(warnings),
            tokens_used=tokens,
        )

    def _find_readings(
        self, prerequisite: Prerequisite, target: Document | None, warnings: list[str]
    ) -> tuple[Citation, ...]:
        """Up to ``READINGS_PER_STEP`` passages, from different texts where
        possible, never from the target text or the news."""
        query = f"{prerequisite.name} {prerequisite.search}".strip()
        result = self._tools.execute_tool(PASSAGE_SEARCH, {"query": query, "limit": SEARCH_LIMIT})
        if not result.success:
            warnings.append(f"Library search for {prerequisite.name} failed: {result.error}")
            return ()
        usable = [
            match for match in result.items
            if match.document.kind != NewsArticle.kind
            and (target is None or match.document.id != target.id)
        ]
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


def describe_text(document: Document) -> str:
    """How a target text is named to the model."""
    year = f" ({document.publication_date.year})" if document.publication_date else ""
    topics = ", ".join(document.topics[:TARGET_TOPICS_SHOWN])
    return f"the text “{document.title}”{year} by {document.author}" + (
        f" (topics: {topics})" if topics else ""
    )
