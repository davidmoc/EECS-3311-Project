"""All prompt wording in one place.

The agent decides *what* to ask; ``PromptBuilder`` decides *how* it is
phrased, so wording can be tuned without touching the agent's logic.
"""

from __future__ import annotations

import re

from praxis.agent.corpus import ResearchCorpus
from praxis.documents import AnnotationType, Document, Passage
from praxis.llm import Prompt
from praxis.reader_model import ExplanationDepth, ReaderProfile

MAX_SEARCH_TERMS = 8
MAX_KNOWLEDGE_LINES = 12
MAX_PLAN_STEPS = 4
PLAN_STEP_KINDS = ("evidence", "theory", "history")

# "history: 1848 revolution, bourgeoisie", optionally bulleted or numbered.
_PLAN_LINE = re.compile(
    r"^\s*(?:[-*•]|\d+[.)])?\s*(evidence|theory|history)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)

RESEARCH_PLAN_RULES = """\
You plan research for Praxis, a platform for studying politics, history and \
Marxist theory from primary sources. The library holds political theory and \
history texts, mostly 19th and early 20th century translations, searched by \
keyword.

Write a research plan of 2 to 4 steps for the reader's question, one step \
per line, in exactly this form:
evidence: <keywords>
theory: <keywords>
history: <keywords>

- evidence: passages that bear directly on the question.
- theory: theoretical concepts needed to analyse it (for example class, \
value, the state).
- history: how the situation or its conditions developed over time.

Use keywords and short phrases in the vocabulary those texts would use, not \
full sentences. Leave out author names. Include at least one evidence step. \
No other text."""

OPEN_QUESTIONS_HEADING = "## Open questions"

RESEARCH_SYNTHESIS_FORMAT = f"""\
Organise the findings under these headings, in this order:
## Findings
## Historical context
## Theoretical connections
## Contradictions
{OPEN_QUESTIONS_HEADING}

Under the first four headings, write prose that cites passages as [1], \
[2]. If the passages say nothing relevant for a heading, write one sentence \
saying so. Under "{OPEN_QUESTIONS_HEADING}", list as "- " bullets two to \
four questions the passages leave unanswered and that further research \
should pursue."""

_PURPOSE_HEADINGS = {
    "evidence": "Retrieved as evidence on the question",
    "theory": "Retrieved for theoretical background",
    "history": "Retrieved for historical development",
    "relation": "Retrieved to investigate a material relation",
    "contradiction": "Retrieved to investigate a contradiction",
}

MAX_FOLLOW_UPS = 3

# Each passage is headed "[18] Author, “Title”, ¶310". A live run cited the
# paragraph number as "[310]", so the difference is spelled out.
CITATION_NUMBER_RULE = """\
- Cite a passage only by the source number in brackets at the start of its \
heading, such as [18]. The ¶ number after the title is the passage's \
paragraph in the original book, not a citation number: never write it in \
brackets."""

ASSESSMENT_RULES = f"""\
You assess research in progress for Praxis, a platform for studying \
politics, history and Marxist theory from primary sources. Analyse the \
numbered passages using historical and dialectical materialism: the material \
conditions, class and production relations, institutions and ideas involved; \
how the situation developed historically; and the contradictions that drive \
it. Then say what is still missing.

Reply only with lines in these forms, one item per line:
relation: <class|production|institutional|ideological> | <who or what is related, and how> [n]
contradiction: <one side> | <the other side> | <how they are related and develop> [n]
development: <a stage or turning point in how the situation developed> [n]
conflict: <how two or more passages disagree> [n, m]
search: <relation|contradiction|history|evidence|theory> | <keywords for a further library search>
question: <a question the passages leave open>
verdict: <sufficient|more research needed>

Rules:
- Every relation, contradiction, development and conflict cites the \
passages it rests on as [n]. Leave out anything the passages do not support.
{CITATION_NUMBER_RULE}
- A conflict cites at least two passages that disagree.
- Propose at most {MAX_FOLLOW_UPS} searches, only for gaps that matter for \
the question, in the vocabulary those texts would use. Do not repeat a \
search already made.
- Write "verdict: sufficient" when the passages already cover the \
question's conditions, history and main contradictions well enough to write \
it up.
- No other text."""

SOURCE_FIRST_RULES = f"""\
You are the research assistant of Praxis, a platform for studying politics, \
history and Marxist theory from primary sources. The reader should engage \
with the sources themselves; your job is to point them to the right \
passages and explain how those passages bear on the question.

Rules:
- Base every claim about what an author or text says on the numbered \
passages provided, and cite them inline as [1], [2] and so on.
- Only cite numbers that appear in the passages. Never invent quotations, \
sources or page references.
{CITATION_NUMBER_RULE}
- If the passages do not answer the question, or only answer part of it, \
say so plainly instead of filling the gap from memory.
- Keep the authors' words and your interpretation distinct: say "the \
passage states" for the text and "this suggests" or similar for analysis.
- Where an interpretation is disputed, say that it is disputed."""

UNCERTAIN_PREFIX = "uncertain:"

ANNOTATION_RULES = f"""\
You annotate texts for readers of Praxis, a platform for studying politics, \
history and Marxist theory from primary sources. The reader is reading the \
text itself; your annotation sits beside one passage of it and helps them \
read that passage. It is shown apart from the author's words and marked as \
AI-generated.

Rules:
- Annotate the passage marked "Passage to annotate". The surrounding \
paragraphs are there so you understand it; do not annotate them.
- Keep the author's words and your commentary distinct: say "the passage \
states" for the text and "this suggests" or similar for interpretation. \
Quote the passage only briefly.
- Other library passages, if given, are numbered; cite them inline as [1], \
[2] when you draw on them. Only cite numbers that appear there. Never \
invent quotations, sources or page references.
{CITATION_NUMBER_RULE}
- You may add background the passages do not contain, but say that it is \
general background, not something the library texts state.
- Where an interpretation is disputed, say that it is disputed.
- After the annotation, for each thing you could not verify from the text \
or the numbered passages and that the reader should check, add one line:
{UNCERTAIN_PREFIX} <what could not be verified>
Write no such line if there is nothing to flag.
- Write plain paragraphs, no headings."""

_ANNOTATION_TASKS = {
    "terminology": (
        "Explain the terms, names and concepts in the passage that a reader "
        "may not know, as the author uses them."
    ),
    "historical_context": (
        "Give the historical context the passage assumes: the events, "
        "conditions, people and institutions it refers to, and when and "
        "why it was written."
    ),
    "argument": (
        "Explain the argument the passage makes: its claim, how it supports "
        "the claim, and how the passage fits the argument of the surrounding "
        "text."
    ),
    "framing": (
        "Identify the ideological framing of the passage: the standpoint it "
        "takes, the assumptions it makes, and what its choice of words or "
        "emphasis does."
    ),
    "fact_check": (
        "Check the factual claims the passage makes (dates, events, figures, "
        "attributions). For each, say whether the numbered passages support "
        "it, whether it is consistent with general historical knowledge, or "
        "whether it cannot be checked. Distinguish factual claims from the "
        "author's interpretation, which is not fact-checked."
    ),
    "connection": (
        "Connect the passage to other texts and ideas: where the same idea "
        "appears, is developed or is disputed elsewhere, especially in the "
        "numbered library passages."
    ),
}

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

    def build_plan_prompt(self, objective: str, profile: ReaderProfile | None = None) -> Prompt:
        system = RESEARCH_PLAN_RULES
        context = reader_context(profile)
        if context:
            system += (
                f"\n\nAbout the reader:\n{context}\n"
                "Add a theory step for a concept the reader is unlikely to know "
                "if the question depends on it."
            )
        return Prompt(system=system, user=objective)

    def build_follow_up_plan_prompt(
        self, objective: str, focus: str, profile: ReaderProfile | None = None
    ) -> Prompt:
        """A plan for continuing earlier research in the direction ``focus``."""
        prompt = self.build_plan_prompt(objective, profile)
        return Prompt(
            system=prompt.system,
            user=(
                f"{objective}\n\nThis question has already been researched. The reader "
                f"now wants to follow up on: {focus}\nPlan steps for the follow-up only."
            ),
        )

    @staticmethod
    def parse_plan(text: str) -> list[tuple[str, str]]:
        """``(kind, keywords)`` pairs from the model's plan, in order.

        Lines not in the expected form are ignored, as are repeats.
        """
        steps: dict[tuple[str, str], None] = {}
        for line in text.splitlines():
            match = _PLAN_LINE.match(line)
            if match:
                keywords = " ".join(match.group(2).strip(" .\"'").split())
                if keywords:
                    steps.setdefault((match.group(1).lower(), keywords), None)
        return list(steps)[:MAX_PLAN_STEPS]

    def build_research_prompt(
        self,
        objective: str,
        corpus: ResearchCorpus,
        purposes: dict[int, str],
        profile: ReaderProfile | None = None,
        unfinished: str | None = None,
        established: list[str] | None = None,
        questions: list[str] | None = None,
    ) -> Prompt:
        """A prompt asking the model to synthesise research findings.

        Sources are grouped by why they were retrieved. ``unfinished``
        explains why research stopped early, so the model says which parts
        are not covered instead of filling them from memory.
        ``established`` and ``questions`` come from the assessments of the
        concrete situation, so the synthesis builds on them.
        """
        if corpus.is_empty:
            raise ValueError("A research prompt needs at least one source.")

        depth = profile.explanation_depth if profile else ExplanationDepth.STANDARD
        system = (
            f"{SOURCE_FIRST_RULES}\n\n{RESEARCH_SYNTHESIS_FORMAT}\n\n"
            f"{_DEPTH_GUIDANCE[depth]}"
        )
        context = reader_context(profile)
        if context:
            system += f"\n\nAbout the reader:\n{context}"

        user = f"Research question: {objective}\n\n"
        if unfinished:
            user += (
                f"Research stopped before every planned step ran: {unfinished}. "
                "Say which parts of the question the passages do not cover.\n\n"
            )
        if established:
            user += (
                "Found while assessing the passages (check each against them "
                "and build on it):\n" + "\n".join(f"- {line}" for line in established) + "\n\n"
            )
        if questions:
            user += (
                "Questions raised during the research:\n"
                + "\n".join(f"- {q}" for q in questions) + "\n\n"
            )
        user += "Passages:\n\n" + _grouped_passages(corpus, purposes)
        return Prompt(system=system, user=user)

    def build_assessment_prompt(
        self,
        objective: str,
        corpus: ResearchCorpus,
        purposes: dict[int, str],
        established: list[str],
        searches_done: list[str],
    ) -> Prompt:
        """A prompt asking the model to assess research in progress.

        ``established`` lists findings from earlier assessments (already in
        "kind: text [n]" form) so the model builds on them instead of
        repeating them; ``searches_done`` lists the searches already made.
        """
        if corpus.is_empty:
            raise ValueError("An assessment prompt needs at least one source.")
        user = f"Research question: {objective}\n\n"
        if searches_done:
            user += "Searches already made:\n" + "\n".join(f"- {s}" for s in searches_done) + "\n\n"
        if established:
            user += (
                "Already established (do not repeat these):\n"
                + "\n".join(f"- {line}" for line in established) + "\n\n"
            )
        user += "Passages:\n\n" + _grouped_passages(corpus, purposes)
        return Prompt(system=ASSESSMENT_RULES, user=user)

    @staticmethod
    def split_open_questions(text: str) -> tuple[str, list[str]]:
        """The synthesis without its open-questions section, and the
        questions listed there."""
        before, heading, after = text.partition(OPEN_QUESTIONS_HEADING)
        if not heading:
            return text.strip(), []
        questions: list[str] = []
        rest: list[str] = []
        in_list = True
        for line in after.splitlines():
            stripped = line.strip()
            if in_list and stripped.startswith("#"):
                in_list = False  # a later section: keep it in the body
            if in_list:
                if stripped[:1] in {"-", "*", "•"}:
                    question = stripped.lstrip("-*• ").strip()
                    if question:
                        questions.append(question)
            else:
                rest.append(line)
        body = before.rstrip()
        if rest:
            body += "\n\n" + "\n".join(rest).strip()
        return body.strip(), questions

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


    def build_annotation_prompt(
        self,
        document: Document,
        passage: Passage,
        surrounding: list[Passage],
        annotation_type: AnnotationType,
        corpus: ResearchCorpus | None = None,
        profile: ReaderProfile | None = None,
    ) -> Prompt:
        """A prompt asking the model to annotate ``passage`` of ``document``.

        ``surrounding`` holds the nearby paragraphs, in order, and may
        include ``passage`` itself (it is then marked in place). ``corpus``
        holds other library passages to draw on, numbered for citation.
        """
        depth = profile.explanation_depth if profile else ExplanationDepth.STANDARD
        system = (
            f"{ANNOTATION_RULES}\n\nTask: {_ANNOTATION_TASKS[annotation_type.value]}\n\n"
            f"{_DEPTH_GUIDANCE[depth]}"
        )
        context = reader_context(profile)
        if context:
            system += f"\n\nAbout the reader:\n{context}"

        year = f" ({document.publication_date.year})" if document.publication_date else ""
        user = f"Text: “{document.title}”{year}, by {document.author}\n\n"
        nearby = surrounding if passage in surrounding else [passage]
        for paragraph in nearby:
            if paragraph == passage:
                user += f"Passage to annotate ({paragraph.locator}):\n<<<\n{paragraph.text}\n>>>\n\n"
            else:
                user += f"({paragraph.locator}) {paragraph.text}\n\n"
        if corpus is not None and not corpus.is_empty:
            user += "Other library passages:\n\n" + "\n\n".join(
                f"{source.label} {source.citation.format()}\n{source.citation.quoted_text}"
                for source in corpus.sources
            )
        else:
            user += "No other library passages were found for this annotation."
        return Prompt(system=system, user=user.rstrip())

    @staticmethod
    def parse_annotation(text: str) -> tuple[str, list[str]]:
        """The annotation without its ``uncertain:`` lines, and what those
        lines say could not be verified, in order and without repeats."""
        body: list[str] = []
        uncertain: dict[str, None] = {}
        for line in text.splitlines():
            stripped = line.strip().lstrip("-*• ").strip()
            if stripped.lower().startswith(UNCERTAIN_PREFIX):
                note = stripped[len(UNCERTAIN_PREFIX):].strip()
                if note:
                    uncertain.setdefault(note, None)
            else:
                body.append(line)
        return "\n".join(body).strip(), list(uncertain)


def _grouped_passages(corpus: ResearchCorpus, purposes: dict[int, str]) -> str:
    """The corpus's passages under headings saying why each was retrieved."""
    groups: dict[str, list[str]] = {}
    for source in corpus.sources:
        purpose = purposes.get(source.number, "evidence")
        groups.setdefault(purpose, []).append(
            f"{source.label} {source.citation.format()}\n{source.citation.quoted_text}"
        )
    return "\n\n".join(
        f"### {_PURPOSE_HEADINGS.get(purpose, purpose)}\n\n" + "\n\n".join(passages)
        for purpose, passages in groups.items()
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
