"""The dialectical-materialist assessment of research in progress (F03, SD01).

``assess`` asks the model, in one call, to read the passages gathered so
far for material relations, historical development, contradictions and
conflicting evidence, and to name what is missing. The model replies in a
fixed line format (see ``ASSESSMENT_RULES`` in ``praxis.agent.prompts``);
``parse_assessment`` turns that into a ``ResearchAssessment``. Lines in any
other form are ignored, so a partly malformed reply still yields whatever
it got right.
"""

from __future__ import annotations

import re

from praxis.agent.corpus import CITATION_MARK, cited_numbers
from praxis.agent.prompts import MAX_FOLLOW_UPS, PromptBuilder
from praxis.llm import LLMClient, LLMError
from praxis.research.assessment import FOLLOW_UP_KINDS, FollowUp, ResearchAssessment
from praxis.research.commands import ResearchContext
from praxis.research.situation import (
    ConcreteSituation,
    ConflictingEvidence,
    Contradiction,
    HistoricalDevelopment,
    MaterialRelation,
    RelationType,
)

# "contradiction: a | b | c [1]", optionally bulleted, numbered or in bold.
_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])?\s*\**\s*([a-z]+)\s*\**\s*:\s*(.+?)\s*$", re.IGNORECASE)

_KINDS = {"relation", "contradiction", "development", "conflict", "search", "question", "verdict"}

_CONNECTIVES = {"vs", "vs.", "versus", "and", "&", "/", "-"}

ASSESSMENT_FAILED = "The research could not be assessed ({}), so the plan was not revised."
ASSESSMENT_UNREADABLE = (
    "The research assessment could not be read, so the plan was not revised."
)


class DialecticalMaterialistResearchMethod:
    def __init__(self, llm: LLMClient | None, prompts: PromptBuilder | None = None) -> None:
        self._llm = llm
        self._prompts = prompts or PromptBuilder()

    @property
    def available(self) -> bool:
        return self._llm is not None

    def assess(
        self, situation: ConcreteSituation, context: ResearchContext
    ) -> ResearchAssessment | None:
        """Assess the situation, or return None (with a warning on the
        session) if the model is missing, fails, or replies unusably."""
        session = context.session
        if self._llm is None or context.corpus.is_empty:
            return None
        prompt = self._prompts.build_assessment_prompt(
            session.objective,
            context.corpus,
            context.purposes,
            established=established_lines(situation),
            searches_done=[
                step.description
                for step in session.steps
                if step.succeeded and not step.is_assessment
            ],
        )
        try:
            response = self._llm.generate(prompt)
        except LLMError as exc:
            session.increment_llm_calls()
            session.add_warning(ASSESSMENT_FAILED.format(exc))
            return None
        session.increment_llm_calls(response.total_tokens)
        assessment = parse_assessment(response.text)
        if assessment is None:
            session.add_warning(ASSESSMENT_UNREADABLE)
            return None
        return assessment


def parse_assessment(text: str) -> ResearchAssessment | None:
    """The assessment in ``text``, or None if no line is in the reply format.

    A reply of only "verdict: sufficient" is a valid, empty assessment.
    """
    relations: list[MaterialRelation] = []
    contradictions: list[Contradiction] = []
    developments: list[HistoricalDevelopment] = []
    conflicts: list[ConflictingEvidence] = []
    follow_ups: dict[FollowUp, None] = {}
    questions: list[str] = []
    verdict: bool | None = None  # True: more research needed
    recognised = False

    for line in text.splitlines():
        match = _LINE.match(line)
        if not match:
            continue
        kind, rest = match.group(1).lower(), match.group(2)
        evidence = tuple(cited_numbers(rest))
        fields = [_clean(part) for part in CITATION_MARK.sub("", rest).split("|")]
        # "conflict: [1] vs [4] | ..." leaves a field of just "vs" once the
        # citation marks are removed.
        fields = [f for f in fields if f and f.lower() not in _CONNECTIVES]
        if not fields:
            continue

        recognised = recognised or kind in _KINDS
        if kind == "relation" and len(fields) >= 2:
            relation_type = _relation_type(fields[0])
            if relation_type:
                relations.append(MaterialRelation(relation_type, " | ".join(fields[1:]), evidence))
        elif kind == "contradiction" and len(fields) >= 2:
            relationship = " | ".join(fields[2:])
            contradictions.append(Contradiction(fields[0], fields[1], relationship, evidence))
        elif kind == "development":
            developments.append(HistoricalDevelopment(" | ".join(fields), evidence))
        elif kind == "conflict":
            conflicts.append(ConflictingEvidence(" | ".join(fields), evidence))
        elif kind == "search":
            follow_up = _follow_up(rest)
            if follow_up:
                follow_ups.setdefault(follow_up, None)
        elif kind == "question":
            questions.append(" | ".join(fields))
        elif kind == "verdict":
            word = fields[0].lower()
            verdict = not (word.startswith("sufficient") or word == "complete")

    if not recognised:
        return None
    chosen = tuple(follow_ups)[:MAX_FOLLOW_UPS]
    return ResearchAssessment(
        relations=tuple(relations),
        contradictions=tuple(contradictions),
        developments=tuple(developments),
        conflicting_evidence=tuple(conflicts),
        follow_ups=chosen,
        unresolved_questions=tuple(questions),
        # Without a verdict, more research is needed if the model asked for it.
        requires_more_research=verdict if verdict is not None else bool(chosen),
    )


def established_lines(situation: ConcreteSituation) -> list[str]:
    """The situation's findings in the reply format, for the next prompt."""

    def marks(evidence: tuple[int, ...]) -> str:
        return f" [{', '.join(map(str, evidence))}]" if evidence else ""

    lines = [f"relation: {r.relation_type.value} | {r.description}{marks(r.evidence)}"
             for r in situation.relations]
    lines += [f"contradiction: {c.pole_a} | {c.pole_b} | {c.relationship}{marks(c.evidence)}"
              for c in situation.contradictions]
    lines += [f"development: {d.description}{marks(d.evidence)}" for d in situation.developments]
    lines += [f"conflict: {c.description}{marks(c.evidence)}" for c in situation.conflicts]
    return lines


def _clean(text: str) -> str:
    return " ".join(text.split()).strip(" .;,\"'*")


def _relation_type(word: str) -> RelationType | None:
    word = word.lower().split()[0] if word.split() else ""
    for relation_type in RelationType:
        if word.startswith(relation_type.value[:5]):  # "institution", "ideology"
            return relation_type
    return None


def _follow_up(rest: str) -> FollowUp | None:
    """``history | Frankfurt assembly`` (or ``history: ...``) as a FollowUp."""
    parts = re.split(r"\s*[|:]\s*", CITATION_MARK.sub("", rest), maxsplit=1)
    if len(parts) != 2:
        return None
    kind, keywords = parts[0].lower().strip(" *"), _clean(parts[1])
    if kind not in FOLLOW_UP_KINDS or not keywords:
        return None
    return FollowUp(kind, keywords)
