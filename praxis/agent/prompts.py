"""All prompt wording in one place.

The agent decides *what* to ask; ``PromptBuilder`` decides *how* it is
phrased, so wording can be tuned without touching the agent's logic.
"""

from __future__ import annotations

import re

from praxis.agent.corpus import ResearchCorpus, Source
from praxis.documents import AnnotationType, Document, Passage
from praxis.llm import Prompt
from praxis.reader_model import ExplanationDepth, ReaderProfile

MAX_SEARCH_TERMS = 8
MAX_KNOWLEDGE_LINES = 12
MAX_PLAN_STEPS = 4
PLAN_STEP_KINDS = ("evidence", "theory", "history")
# Compared sources are called Source A, Source B, ...
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

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
    "event": "News reports of the event being researched",
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
[2] when you draw on them, never by their ¶ number. Only cite numbers that \
appear there. Never invent quotations, sources or page references.
- You may refer to the passage and the surrounding paragraphs by their ¶ \
number. Never refer to any other paragraph of the text: you have not seen \
it.
{CITATION_NUMBER_RULE}
- You may add background the passages do not contain, but say that it is \
general background, not something the library texts state.
- Where an interpretation is disputed, say that it is disputed.
- After the annotation, for each thing you could not verify from the text \
or the numbered passages and that the reader should check, add one line:
{UNCERTAIN_PREFIX} <what could not be verified>
Write no such line if there is nothing to flag.
- Write plain paragraphs, no headings."""

COMPARISON_RULES = f"""\
You compare sources for readers of Praxis, a platform for studying politics, \
history and Marxist theory from primary sources. The reader chose the \
sources and will read the passages beside your comparison, so point them to \
what to look at; do not summarise the sources for them.

Compare how the sources treat the subject: shared ground; differences in \
terminology, emphasis, framing, assumptions, omitted context, and the \
evidence or authorities relied on; and factual claims on which they \
contradict each other.

Reply only with lines in these forms, one item per line:
comparability: <comparable|partly comparable|not comparable> | <why>
similarity: <what the sources share> [n, m]
difference: <terminology|emphasis|framing|assumptions|omission|evidence> | <how the sources differ> [n, m]
disagreement: <a factual claim on which the sources contradict each other> [n, m]
observation: <your interpretation of one source's standpoint or framing> [n]
{UNCERTAIN_PREFIX} <something the reader should check that the passages cannot settle>

Rules:
- Start with the comparability line. If the passages address substantially \
different aspects of the subject, write "not comparable" and say why: a \
direct comparison would mislead. Then write no other line except \
{UNCERTAIN_PREFIX} lines.
- Every similarity, difference and disagreement cites passages from at \
least two different sources as [n]. Every observation cites the passages it \
rests on. Leave out anything the passages do not support.
{CITATION_NUMBER_RULE}
- A disagreement is about facts (dates, events, figures, who did what): \
the sources make incompatible claims about the same place, time and \
people. Claims about different countries, periods or groups do not \
disagree. A difference in how the same facts are described, defined, \
weighed or explained is a difference, not a disagreement.
- Judgements about bias or a source's standpoint are observations: \
interpretation, never stated as fact.
- Use only the source details given. Do not state or guess who owns, funds \
or employs a source unless those details say so.
- Write at most 4 lines of each kind.
- No other text."""

EVENT_SUMMARY_RULES = """\
You write the event cards of a news dashboard for Praxis, a platform for \
studying politics and history. A card gives the reader an at-a-glance \
account of one event; the reports it rests on are listed under it.

Reply only with lines in these forms:
title: <a short, neutral title for the event>
summary: <two or three sentences on what happened, citing the reports as [n]>
category: <one to three of: politics, economy, labour, conflict, diplomacy, environment, rights, society, other>
same event: <yes|partly|no> | <why, unless yes>

Rules:
- Use only what the numbered reports say. Do not add background or \
figures from memory.
- Cite every sentence of the summary with the reports it rests on, as [1] \
or [1, 3].
- Where reports give different figures or accounts of a fact, say so and \
cite each; do not pick one.
- Attribute contested claims to whoever makes them ("officials said"). Do \
not adopt one outlet's framing or loaded words as your own.
- If the reports are not all about the same event, write "same event: no" \
or "partly", and summarise only the event of report [1].
- No other text."""

EVENT_EXPLORATION_RULES = f"""\
You expand a news event for readers of Praxis, a platform for studying \
politics, history and Marxist theory from primary sources. The reader has \
the reports and passages beside your account and can open them.

Write these sections, in this order:
## What happened
## Where the reports differ
## Background from the library
{OPEN_QUESTIONS_HEADING}

Rules:
- "What happened" uses only the numbered reports, and cites them as [1], \
[2]. Do not add facts, figures or background from memory.
- "Where the reports differ": set out each report's account of any fact \
they disagree on, with its citation; do not decide which is right. Note \
differences in emphasis or wording that change the picture. If they do \
not differ, say so in one sentence.
- "Background from the library": the library passages are political \
theory and history, mostly from the 19th and early 20th centuries. Use \
them only where they genuinely bear on the event, cite them, and present \
the connection as interpretation. If none bear on it, say so in one \
sentence.
- Under "{OPEN_QUESTIONS_HEADING}", list as "- " bullets two to four \
questions the reports leave unanswered.
{CITATION_NUMBER_RULE}
- Attribute contested claims to whoever makes them. Do not adopt one \
outlet's framing as your own."""

MAX_RECOMMENDATIONS = 5
MAX_EXTERNAL_SUGGESTIONS = 3
DIFFICULTIES = ("introductory", "intermediate", "advanced")

RECOMMENDATION_RULES = f"""\
You recommend readings for Praxis, a platform for studying politics, \
history and Marxist theory from primary sources. The candidates are texts \
in the reader's library that matched their topic; each is shown with the \
passages that matched and, where known, how far the reader has read it.

Reply only with lines in these forms, best recommendation first:
recommend: [n] | <introductory|intermediate|advanced> | <why this text is worth reading for the topic>
external: <title> | <author> | <why>

Rules:
- Recommend at most {MAX_RECOMMENDATIONS} candidates, and only those that \
genuinely bear on the topic. Leave out a candidate whose passages only \
mention the topic in passing.
- Cite a candidate only by its number in brackets, such as [2].
- The difficulty is how demanding the text is for a reader new to the \
topic, judged from its passages and kind.
- Base each reason on the candidate's passages and details. Do not \
describe a text's contents beyond what they show, except for widely known \
facts about the work, which you present as general background.
- Prefer texts the reader has not finished; recommend a finished text \
only if it is clearly the best on the topic. The reader's progress is \
shown beside each recommendation, so do not restate it in the reason.
- If what is known about the reader is given, say in the reason how the \
text fits them (for example, that it builds on what they know). If \
nothing about the reader is given, do not claim it suits them personally.
- Write external lines (at most {MAX_EXTERNAL_SUGGESTIONS}) only for \
well-known works that the library lacks and that the topic clearly needs. \
Name only real works you are confident exist.
- No other text."""

MAX_PREREQUISITES = 6
PREREQUISITE_KINDS = ("concept", "event", "theory", "text")

PREREQUISITE_RULES = f"""\
You plan learning paths for Praxis, a platform for studying politics, \
history and Marxist theory from primary sources. The reader wants to \
understand a target topic or text. Name what it assumes they already \
understand: concepts, historical events, theories or earlier texts. The \
reader will build that background from library passages instead of being \
given a simplified answer.

Reply only with blocks like this, one per prerequisite, ordered so that \
each comes before anything that builds on it:
prerequisite: <short name> | <concept|event|theory|text> | <essential|helpful>
search: <keywords for finding it in the library>
why: <one or two sentences on why the target assumes it>
orientation: <two or three sentences of basic orientation, for when the library has nothing on it>

Rules:
- Name 2 to {MAX_PREREQUISITES} prerequisites, only ones the target \
genuinely assumes. Do not include the target itself.
- "essential" means the target cannot be understood without it; \
"helpful" means it deepens understanding.
- Search keywords use the vocabulary of 19th and early 20th century \
political texts in translation, not modern summaries. Leave out author \
names.
- If topics the reader already knows are listed and a prerequisite is \
one of them, use exactly that name for it.
- The orientation is general background, not a summary of the target. \
Where an interpretation is disputed, say so.
- No other text."""

MAX_HISTORY_SEARCHES = 4

HISTORY_PLAN_RULES = f"""\
You plan the search for historical context in Praxis, a platform for \
studying politics, history and Marxist theory from primary sources. The \
library holds political theory and history texts, mostly 19th and early \
20th century translations, searched by keyword. The reader wants to \
understand how a situation developed over time.

Reply only with lines in these forms:
scope: <focused|too broad> | <if too broad: two or three narrower topics, separated by ;>
search: <the period, stage or aspect to look for> | <keywords>

Rules:
- Write "too broad" only when the topic spans so much (for example a \
whole century, or "the history of capitalism") that a short account from \
a few passages would mislead. Then write no search lines.
- Otherwise write 2 to {MAX_HISTORY_SEARCHES} search lines, from the \
origins to the latest developments. Keep each period label short, and \
give at most six keywords, in the vocabulary those texts would use. \
Leave out author names.
- No other text."""

HISTORY_RULES = f"""\
You organise historical context for readers of Praxis, a platform for \
studying politics, history and Marxist theory from primary sources. The \
reader will read the numbered passages beside your account, so organise \
what they show; do not retell history from memory.

Reply only with lines in these forms, one item per line:
overview: <two or three sentences on how the situation developed> [n]
origin: <a condition or event the situation grew out of> [n]
stage: <when> | <a stage of the development> [n]
turning point: <when> | <what changed, and why it mattered> [n]
continuity: <what persisted through the changes> [n]
interpretation: <an interpretation that is disputed, and whose it is> [n]
gap: <something the passages do not cover that the account would need>

Rules:
- Every line except gap lines cites the passages it rests on as [n]. \
Leave out anything the passages do not support.
{CITATION_NUMBER_RULE}
- Stages and turning points are facts the passages state: dates, events, \
who did what. Write them as one sequence in chronological order, mixing \
the two kinds, and never list one event as both: a turning point is a \
stage that changed the course. Write the date as the passages give it; \
if they give none, write "undated".
- An explanation of why something happened that historians or the \
authors dispute, or that is the author's own judgement, is an \
interpretation, never a stage or turning point. Say whose view it is.
- News reports, if given, describe the present situation; the history \
comes from the library passages.
- Write at most 6 lines of each kind.
- No other text."""

MAX_CONCEPTS = 4

CONCEPT_RULES = f"""\
You choose theory for an analysis in Praxis, a platform for studying \
politics, history and Marxist theory from primary sources. Given an issue \
and the evidence gathered on it, name the Marxist concepts that genuinely \
help explain it (for example class, labour, capital, ownership, the state, \
imperialism, ideology, material conditions), so that theoretical passages \
can be found in the library.

Reply only with lines in this form:
concept: <concept> | <keywords for finding it in the library> | <why it bears on this evidence>

Rules:
- Name 1 to {MAX_CONCEPTS} concepts, only those the evidence gives reason \
to apply. Do not force the issue into a concept the evidence does not \
support.
- If the reader asked for a particular framework, include its concepts \
first.
- Keywords use the vocabulary of 19th and early 20th century Marxist \
texts in translation, at most six. Leave out author names.
- No other text."""

ANALYSIS_RULES = f"""\
You write Marxist theoretical analysis for readers of Praxis, a platform \
for studying politics, history and Marxist theory from primary sources. \
Analyse the issue using historical and dialectical materialism, \
connecting the theoretical passages to the evidence passages. The reader \
reads the passages beside your analysis.

Reply only with lines in these forms, one item per line:
condition: <material|class|production|institution|ideology|development|contradiction> | <what the evidence shows> [n]
application: <concept> | <how the theory passage applies to the evidence> [n, m]
claim: <supported|tentative> | <an interpretation the analysis reaches> [n, m]
alternative: <another plausible reading within Marxist analysis> [n]
limit: <where a concept does not fit, or the evidence is too thin>

Rules:
- Conditions rest on evidence passages only. An application cites at \
least one theory passage and at least one evidence passage.
{CITATION_NUMBER_RULE}
- Every condition, application, claim and alternative cites the passages \
it rests on as [n]. Leave out anything they do not support.
- A claim is "supported" only if several evidence passages bear it out; \
otherwise it is "tentative". Interpretations are never stated as \
uncontested fact.
- Where Marxists would read the evidence differently, give the \
alternative. Where a concept does not fit, say so in a limit line rather \
than forcing it.
- Write at most 5 lines of each kind.
- No other text."""

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

    def build_comparison_prompt(
        self,
        subject: str,
        sources: list[tuple[str, list[Source]]],
        profile: ReaderProfile | None = None,
    ) -> Prompt:
        """A prompt asking the model to compare ``sources`` on ``subject``.

        Each entry is a source's description (from its ``SourceProfile``)
        and its passages, numbered across all sources.
        """
        if len(sources) < 2 or any(not passages for _, passages in sources):
            raise ValueError("A comparison prompt needs passages from at least two sources.")
        system = COMPARISON_RULES
        context = reader_context(profile)
        if context:
            system += f"\n\nAbout the reader:\n{context}"
        user = f"Compare the sources on: {subject}\n\n"
        for letter, (description, passages) in zip(_LETTERS, sources):
            user += f"### Source {letter}: {description}\n\n" + "\n\n".join(
                f"{source.label} {source.citation.locator}\n{source.citation.quoted_text}"
                for source in passages
            ) + "\n\n"
        return Prompt(system=system, user=user.rstrip())

    def build_event_summary_prompt(self, reports: list[tuple[str, str, str, str]]) -> Prompt:
        """A prompt asking for an event card. ``reports`` are (outlet, date,
        headline, summary) in the order they are numbered."""
        if not reports:
            raise ValueError("An event summary needs at least one report.")
        user = "Reports:\n\n" + "\n\n".join(
            f"[{n}] {outlet}, {when}\nHeadline: {headline}\n{summary or '(no summary in the feed)'}"
            for n, (outlet, when, headline, summary) in enumerate(reports, start=1)
        )
        return Prompt(system=EVENT_SUMMARY_RULES, user=user)

    def build_event_exploration_prompt(
        self,
        headline: str,
        reports: list[tuple[str, str, str, str, str]],
        passages: list[tuple[str, str, str]],
        developing: bool = False,
    ) -> Prompt:
        """A prompt for the expanded event view. ``reports`` are (label,
        outlet, date, headline, summary); ``passages`` are (label, citation,
        text) of library passages."""
        if not reports:
            raise ValueError("An event needs at least one report.")
        user = f"Event: {headline}\n\n"
        if developing:
            user += "The event is recent and may still be developing; say where the reports are provisional.\n\n"
        user += "Reports:\n\n" + "\n\n".join(
            f"{label} {outlet}, {when}\nHeadline: {title}\n{text or '(no summary in the feed)'}"
            for label, outlet, when, title, text in reports
        )
        if passages:
            user += "\n\nLibrary passages:\n\n" + "\n\n".join(
                f"{label} {citation}\n{text}" for label, citation, text in passages
            )
        else:
            user += "\n\nNo library passages were found for this event."
        return Prompt(system=EVENT_EXPLORATION_RULES, user=user)

    def build_recommendation_prompt(
        self,
        topic: str,
        candidates: list[tuple[str, str]],
        profile: ReaderProfile | None = None,
    ) -> Prompt:
        """A prompt asking the model to rank ``candidates`` for ``topic``.

        Each candidate is (heading, body): the heading starts with its
        ``[n]`` label; the body gives its details and matching passages.
        With no candidates, the model can only suggest works outside the
        library.
        """
        system = RECOMMENDATION_RULES
        context = reader_context(profile)
        if context:
            system += f"\n\nAbout the reader:\n{context}"
        if not candidates:
            # Only external suggestions are possible (UC07's alternative flow).
            return Prompt(system=system, user=f"Topic: {topic}\n\nNo text in the library matched this topic.")
        user = f"Topic: {topic}\n\nCandidates:\n\n" + "\n\n".join(
            f"{heading}\n{body}" for heading, body in candidates
        )
        return Prompt(system=system, user=user)

    def build_prerequisite_prompt(self, target: str, known_topics: list[str]) -> Prompt:
        """A prompt asking what ``target`` assumes. ``known_topics`` are the
        reader's known topics, listed so the model reuses their names and
        the service can filter them out; empty when personalization does
        not apply."""
        user = f"Target: {target}"
        if known_topics:
            user += "\n\nTopics the reader already knows: " + "; ".join(known_topics)
        return Prompt(system=PREREQUISITE_RULES, user=user)

    def build_history_plan_prompt(self, topic: str) -> Prompt:
        return Prompt(system=HISTORY_PLAN_RULES, user=f"Topic: {topic}")

    def build_history_prompt(
        self,
        topic: str,
        corpus: ResearchCorpus,
        purposes: dict[int, str],
        profile: ReaderProfile | None = None,
    ) -> Prompt:
        """A prompt asking the model to organise the corpus's passages
        into origins, stages, turning points and interpretations."""
        if corpus.is_empty:
            raise ValueError("A history prompt needs at least one source.")
        system = HISTORY_RULES
        context = reader_context(profile)
        if context:
            system += f"\n\nAbout the reader:\n{context}"
        return Prompt(
            system=system,
            user=f"Topic: {topic}\n\nPassages:\n\n{_grouped_passages(corpus, purposes)}",
        )

    def build_concept_prompt(
        self, issue: str, evidence: list[Source], framework: str | None = None
    ) -> Prompt:
        """A prompt asking which concepts apply, given the evidence."""
        user = f"Issue: {issue}"
        if framework:
            user += f"\n\nThe reader asked for this framework: {framework}"
        if evidence:
            user += "\n\nEvidence:\n\n" + "\n\n".join(
                f"{source.label} {source.citation.format()}\n{source.citation.quoted_text}"
                for source in evidence
            )
        else:
            user += "\n\nNo evidence passages were found."
        return Prompt(system=CONCEPT_RULES, user=user)

    def build_analysis_prompt(
        self,
        issue: str,
        corpus: ResearchCorpus,
        purposes: dict[int, str],
        framework: str | None = None,
        established: list[str] = (),
        profile: ReaderProfile | None = None,
    ) -> Prompt:
        """A prompt asking for the analysis. ``established`` are findings
        a research session already made, offered as context."""
        if corpus.is_empty:
            raise ValueError("An analysis prompt needs at least one source.")
        system = ANALYSIS_RULES
        context = reader_context(profile)
        if context:
            system += f"\n\nAbout the reader:\n{context}"
        user = f"Issue: {issue}"
        if framework:
            user += f"\n\nThe reader asked for this framework: {framework}"
        if established:
            user += "\n\nFindings the research already established:\n" + "\n".join(
                f"- {line}" for line in established
            )
        user += f"\n\nPassages:\n\n{_grouped_passages(corpus, purposes)}"
        return Prompt(system=system, user=user)

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
