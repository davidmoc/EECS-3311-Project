"""Personalized and adaptive assistance (F14, UC14, SD07; Stage 1's
``PersonalizationService``).

Every feature that asks the model for an explanation passes the reader's
profile here to decide what the prompt may say about them:

- what they are recorded as knowing about *this request's topic* comes
  first (UC14 step 2, "determines the user's likely familiarity with the
  current topic"), so known material is not re-explained (step 3);
- when nothing is recorded about the topic, the model is told not to
  assume familiarity (step 4, "identified knowledge gaps are considered");
- inferred knowledge is worded as a guess ("low confidence … is not
  treated as certain");
- nothing is said when little is known or personalization is off ("the
  system provides a general response").

``RequestPreferences`` are the reader's overrides for one request: more
or less detail, or no personalization at all ("The user can override the
level of detail"). They change a copy of the profile, never the stored one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from praxis.reader_model.models import ExplanationDepth, KnowledgeArea, ReaderProfile

if TYPE_CHECKING:  # the service module imports persistence
    from praxis.reader_model.service import ReaderProfileService

MAX_KNOWLEDGE_LINES = 12
MAX_INTERESTS = 5

NOTHING_ON_TOPIC = (
    "- Nothing is recorded about what they know of this topic: do not "
    "assume they know it, and define its basic terms."
)
PITCH = (
    "Pitch the explanation to this reader: skip what they already know, "
    "define terms they are unlikely to know."
)

# Words that say nothing about a topic ("the history of the state").
_STOPWORDS = frozenset(
    "about after against also among and are between both but by did does "
    "for from had has have how into its not of off once only other over "
    "same should some such than that the their them then there these they "
    "this those through under until very was were what when where which "
    "while who whom why will with would".split()
)
_WORD = re.compile(r"[a-z][a-z'-]+")


@dataclass(frozen=True)
class RequestPreferences:
    """The reader's overrides for one request."""

    depth: ExplanationDepth | None = None
    personalized: bool = True

    def apply(self, profile: ReaderProfile) -> ReaderProfile:
        """A copy of ``profile`` as this request should see it."""
        return replace(
            profile,
            explanation_depth=self.depth or profile.explanation_depth,
            personalization_enabled=profile.personalization_enabled and self.personalized,
        )


@dataclass(frozen=True)
class Familiarity:
    """What the reader is recorded as knowing, split by whether it bears
    on the request's topic. Both are ordered strongest first."""

    relevant: tuple[KnowledgeArea, ...]
    others: tuple[KnowledgeArea, ...]


def topic_words(text: str) -> set[str]:
    """The words of ``text`` that name its subject, singular and lower
    case: "the Paris Communes" gives {"paris", "commune"}."""
    words = set()
    for word in _WORD.findall(text.casefold()):
        word = word.removesuffix("'s").strip("'-")
        if len(word) < 3 or word in _STOPWORDS:
            continue
        # "communes" → "commune", but not "class", "analysis" or "bonus".
        if len(word) > 4 and word.endswith("s") and not word.endswith(("ss", "is", "us")):
            word = word[:-1]
        words.add(word)
    return words


class PersonalizationService:
    """Profiles as a request should see them, and what prompts may say
    about the reader."""

    def __init__(self, profiles: ReaderProfileService) -> None:
        self._profiles = profiles

    def profile_for(self, preferences: RequestPreferences | None = None) -> ReaderProfile:
        """The stored profile with this request's overrides applied."""
        profile = self._profiles.get_profile()
        return preferences.apply(profile) if preferences else profile

    @staticmethod
    def determine_explanation_depth(profile: ReaderProfile | None) -> ExplanationDepth:
        return profile.explanation_depth if profile else ExplanationDepth.STANDARD

    @staticmethod
    def familiarity(profile: ReaderProfile, topic: str | None = None) -> Familiarity:
        areas = sorted(profile.knowledge.areas.values(), key=lambda a: (-a.level, a.topic))
        if not topic:
            return Familiarity((), tuple(areas))
        wanted = topic_words(topic)
        relevant = tuple(a for a in areas if topic_words(a.topic) & wanted)
        return Familiarity(relevant, tuple(a for a in areas if a not in relevant))

    @classmethod
    def personalize_prompt(
        cls, profile: ReaderProfile | None, topic: str | None = None
    ) -> str | None:
        """What the prompt may say about the reader, or None to stay
        general. With ``topic``, knowledge of that topic comes first, and
        the model is told when none is recorded."""
        if profile is None or not profile.personalization_enabled or profile.is_sparse:
            return None

        lines = []
        if profile.background:
            lines.append(f"- In their own words: {profile.background}")
        familiarity = cls.familiarity(profile, topic)
        if topic:
            if familiarity.relevant:
                lines.append("On this topic:")
                lines.extend(_knowledge_line(a) for a in familiarity.relevant[:MAX_KNOWLEDGE_LINES])
            else:
                lines.append(NOTHING_ON_TOPIC)
            room = MAX_KNOWLEDGE_LINES - len(familiarity.relevant)
            if familiarity.others and room > 0:
                lines.append("Other knowledge:")
                lines.extend(_knowledge_line(a) for a in familiarity.others[:room])
        else:
            lines.extend(_knowledge_line(a) for a in familiarity.others[:MAX_KNOWLEDGE_LINES])
        interests = profile.interests.top(MAX_INTERESTS)
        if interests:
            lines.append(f"- Interested in: {', '.join(interests)}")
        if not lines:
            return None
        lines.append(PITCH)
        return "\n".join(lines)


def _knowledge_line(area: KnowledgeArea) -> str:
    level = area.level.name.lower()
    if area.is_inferred:
        return f"- Probably at {level} level in {area.topic} (inferred from reading)"
    return f"- Says they are at {level} level in {area.topic}"
