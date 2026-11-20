"""All prompt wording in one place.

The agent decides *what* to ask; ``PromptBuilder`` decides *how* it is
phrased, so wording can be tuned without touching the agent's logic.
"""

from __future__ import annotations

import re

from praxis.agent.corpus import ResearchCorpus
from praxis.llm import Prompt
from praxis.reader_model import ExplanationDepth, ReaderProfile

MAX_SEARCH_TERMS = 8
MAX_KNOWLEDGE_LINES = 12

SOURCE_FIRST_RULES = """\
You are the research assistant of Praxis, a platform for studying politics, \
history and Marxist theory from primary sources. The reader should engage \
with the sources themselves; your job is to point them to the right \
passages and explain how those passages bear on the question.

Rules:
- Base every claim about what an author or text says on the numbered \
passages provided, and cite them inline as [1], [2] and so on.
- Only cite numbers that appear in the passages. Never invent quotations, \
sources or page references.
- If the passages do not answer the question, or only answer part of it, \
say so plainly instead of filling the gap from memory.
- Keep the authors' words and your interpretation distinct: say "the \
passage states" for the text and "this suggests" or similar for analysis.
- Where an interpretation is disputed, say that it is disputed."""

_DEPTH_GUIDANCE = {
    ExplanationDepth.BRIEF: "Keep the explanation short: two or three sentences.",
    ExplanationDepth.STANDARD: "Keep the explanation to one or two paragraphs.",
    ExplanationDepth.DETAILED: (
        "Give a detailed explanation, several paragraphs if the passages "
        "support it."
    ),
}


class PromptBuilder:
    def build_search_terms_prompt(self, question: str) -> Prompt:
        return Prompt(
            system=(
                "You turn a reader's question into search keywords for a "
                "library of political theory and history texts, mostly 19th "
                "and early 20th century translations. Reply with one line of "
                "at most 8 comma-separated keywords or short phrases, using "
                "the vocabulary those texts would use. Leave out author names "
                "unless the question is about the author's life. No other text."
            ),
            user=question,
        )

    @staticmethod
    def parse_search_terms(text: str) -> list[str]:
        """Keywords from the model's reply, deduplicated, in order."""
        terms = [t.strip(" .\"'*-") for t in re.split(r"[,\n;]", text)]
        unique = dict.fromkeys(t for t in terms if t)
        return list(unique)[:MAX_SEARCH_TERMS]

    def build_question_prompt(
        self,
        question: str,
        corpus: ResearchCorpus,
        profile: ReaderProfile | None = None,
    ) -> Prompt:
        """A prompt asking the model to explain the corpus's passages.

        ``profile`` is used only when personalization is appropriate; see
        ``reader_context``.
        """
        if corpus.is_empty:
            raise ValueError("A question prompt needs at least one source.")

        passages = "\n\n".join(
            f"{source.label} {source.citation.format()}\n{source.citation.quoted_text}"
            for source in corpus.sources
        )
        depth = profile.explanation_depth if profile else ExplanationDepth.STANDARD
        system = f"{SOURCE_FIRST_RULES}\n\n{_DEPTH_GUIDANCE[depth]}"
        context = reader_context(profile)
        if context:
            system += f"\n\nAbout the reader:\n{context}"

        return Prompt(
            system=system,
            user=f"Question: {question}\n\nPassages:\n\n{passages}",
        )


def reader_context(profile: ReaderProfile | None) -> str | None:
    """What the prompt may say about the reader, or None to stay general.

    Nothing is said when the reader turned personalization off or when too
    little is known to adapt honestly (F14). Inferred knowledge is worded as
    a guess, because the reader never confirmed it (F13).
    """
    if profile is None or not profile.personalization_enabled or profile.is_sparse:
        return None

    lines = []
    if profile.background:
        lines.append(f"- In their own words: {profile.background}")
    areas = sorted(
        profile.knowledge.areas.values(), key=lambda a: (-a.level, a.topic)
    )[:MAX_KNOWLEDGE_LINES]
    for area in areas:
        level = area.level.name.lower()
        if area.is_inferred:
            lines.append(f"- Probably at {level} level in {area.topic} (inferred from reading)")
        else:
            lines.append(f"- Says they are at {level} level in {area.topic}")
    interests = profile.interests.top(5)
    if interests:
        lines.append(f"- Interested in: {', '.join(interests)}")
    if not lines:
        return None
    lines.append(
        "Pitch the explanation to this reader: skip what they already know, "
        "define terms they are unlikely to know."
    )
    return "\n".join(lines)
