"""Each feature's result as Markdown for the research page.

The GUI's counterparts of the CLI's ``_print_answer``, ``_print_research``,
``_print_history`` and so on. Only formatting: what is shown, and how it is
labelled, follows the CLI, so both interfaces say the same things about
what is AI-generated, tentative or unchecked.
"""

from __future__ import annotations

from praxis.agent import AgentResponse, ResponseStatus
from praxis.comparison import Comparability, SourceComparison
from praxis.gui.render import SHOWN_PASSAGE_CHARS, ai_heading, ai_text, escape, join, labels, line, read_link, sources, warnings
from praxis.reading import LearningPath, ReadingStatus, RecommendationResult
from praxis.reading.prerequisites import StepStatus
from praxis.reading.traditions import StatementKind, TraditionsComparison, TraditionsStatus
from praxis.research.analysis import AnalysisItemKind, AnalysisStatus, MaterialistAnalysis
from praxis.research.history import ContextStatus, HistoricalContext, HistoryItemKind, SuggestedReading
from praxis.research.result import ResearchResult

READING_EXCERPT_CHARS = 220


def answer(response: AgentResponse) -> str:
    """F04: the passages first, then the explanation."""
    parts = [f"## {escape(response.question)}", sources(response.sources, response.cited)]
    if response.status is ResponseStatus.ANSWERED and response.explanation:
        parts.append(ai_text("Explanation", response.explanation, response.personalized))
    parts.append(warnings(response.warnings, response.tokens_used))
    return join(*parts)


def research(result: ResearchResult) -> str:
    """F03: the steps taken, the sources, what was established, the analysis."""
    steps = []
    for number, step in enumerate(result.session.steps, start=1):
        mark = "✓" if step.succeeded else "✗"
        detail = f" (+{len(step.new_sources)} sources)" if step.new_sources else ""
        if step.error:
            detail += f" — {step.error}"
        steps.append(f"{number}. {mark} {escape(step.description + detail)}")
    if result.stop_reason:
        steps.append(f"\n*Stopped: {escape(result.stop_reason.value)}.*")
    parts = [
        f"## {escape(result.objective)}",
        f"*Research session {str(result.session.id)[:8]}*",
        "### Research steps\n\n" + "\n".join(steps),
        sources(result.sources, result.cited, result.purposes),
    ]
    situation = result.situation
    if situation is not None and situation.has_findings:
        sections = (
            ("Contradictions", [(c.description, c.evidence) for c in situation.contradictions]),
            ("Material relations", [(f"({r.relation_type.value}) {r.description}", r.evidence)
                                    for r in situation.relations]),
            ("Historical development", [(d.description, d.evidence) for d in situation.developments]),
            ("Where the sources disagree", [(c.description, c.evidence) for c in situation.conflicts]),
        )
        block = ["### Concrete situation (AI-assessed; each point cites the sources above)"]
        for title, items in sections:
            if items:
                block.append(f"**{title}**\n\n" + "\n".join(line(text, evidence) for text, evidence in items))
        parts.append("\n\n".join(block))
    if result.status is ResponseStatus.ANSWERED and result.summary:
        parts.append(ai_text("Analysis", result.summary, result.personalized))
    if result.open_questions:
        parts.append("### Open questions (AI-generated)\n\n" + "\n".join(line(q) for q in result.open_questions))
    readings = result.get_recommended_readings()
    if readings:
        parts.append("### Further reading\n\n" + "\n".join(
            f"- {escape(r.title)} — {escape(r.author)} ({read_link(r.document_id)})" for r in readings
        ))
    parts.append(warnings(result.warnings, result.session.tokens_used))
    return join(*parts)


def _readings(title: str, readings: tuple[SuggestedReading, ...]) -> str:
    if not readings:
        return ""
    return f"### {title}\n\n" + "\n".join(
        f"- {escape(r.title)} — {escape(r.author)}, cited {r.cited} time{'s' if r.cited != 1 else ''} "
        f"({read_link(r.document_id, r.start)})"
        for r in readings
    )


def history(context: HistoricalContext) -> str:
    """F09: origins, a dated chronology, continuities, disputed views, gaps."""
    if context.status is ContextStatus.TOO_BROAD:
        parts = [
            f"## {escape(context.topic)}",
            "This covers too much to trace well from a few library passages. "
            "Narrow it, for example (AI-suggested):",
            "\n".join(line(topic) for topic in context.narrower),
            "Or tick “Trace even if broad” and run it again.",
            warnings(context.warnings, context.tokens_used),
        ]
        return join(*parts)
    parts = [f"## Historical context: {escape(context.topic)}", sources(context.sources, context.cited, context.purposes)]
    if context.status is ContextStatus.EXPLAINED:
        parts.append(ai_heading("How it developed, organised from the passages", context.personalized))
        if context.overview:
            parts.append(f"{escape(context.overview)} {labels(context.overview_evidence)}")
        for kind, title in (
            (HistoryItemKind.ORIGIN, "Origins"),
            (None, "Chronology (as the passages state it)"),
            (HistoryItemKind.CONTINUITY, "Continuities"),
            (HistoryItemKind.INTERPRETATION, "Disputed interpretations (interpretation, not established fact)"),
        ):
            if kind is None:
                items = [
                    (f"{i.when}: {'turning point — ' if i.kind is HistoryItemKind.TURNING_POINT else ''}{i.text}",
                     i.evidence)
                    for i in context.items if i.kind.is_dated
                ]
            else:
                items = [(i.text, i.evidence) for i in context.of_kind(kind)]
            if items:
                parts.append(f"**{title}**\n\n" + "\n".join(line(text, evidence) for text, evidence in items))
        if context.gaps:
            parts.append("**Gaps: what the passages do not cover**\n\n" + "\n".join(line(g) for g in context.gaps))
        parts.append(_readings("Read further", context.readings))
    parts.append(warnings(context.warnings, context.tokens_used))
    return join(*parts)


_CLAIM_LABELS = {"supported": "supported by several passages", "tentative": "tentative"}


def analysis(result: MaterialistAnalysis) -> str:
    """F11: conditions, theory applied to evidence, claims marked supported
    or tentative, other readings and limits."""
    parts = [f"## Marxist analysis: {escape(result.issue)}"]
    if result.framework:
        parts.append(f"Framework requested: {escape(result.framework)}")
    if result.concepts:
        parts.append("Concepts applied (AI-chosen): " + escape("; ".join(c.name for c in result.concepts)))
    parts.append(sources(result.sources, result.cited, result.purposes))
    if result.status is AnalysisStatus.ANALYSED:
        parts.append(ai_heading("Analysis, an AI-generated interpretation", result.personalized))
        for kind, title in (
            (AnalysisItemKind.CONDITION, "What the evidence shows"),
            (AnalysisItemKind.APPLICATION, "Theory applied to the evidence"),
            (AnalysisItemKind.CLAIM, "Interpretations"),
            (AnalysisItemKind.ALTERNATIVE, "Other readings within Marxist analysis"),
        ):
            items = result.of_kind(kind)
            if not items:
                continue
            rows = []
            for item in items:
                if kind is AnalysisItemKind.CLAIM:
                    prefix = f"({_CLAIM_LABELS[item.label]}) "
                else:
                    prefix = f"{item.label}: " if item.label else ""
                rows.append(line(prefix + item.text, item.evidence))
            parts.append(f"**{title}**\n\n" + "\n".join(rows))
        if result.limits:
            parts.append("**Limits: where the theory may not fit or the evidence is thin**\n\n"
                         + "\n".join(line(limit) for limit in result.limits))
        parts.append(_readings("Theory to study further", result.readings))
    parts.append(warnings(result.warnings, result.tokens_used))
    return join(*parts)


_STATEMENT_TITLES = {
    StatementKind.POSITION: "Position",
    StatementKind.CONDITIONS: "Conditions it developed in",
    StatementKind.ASSESSMENT: "Marxist assessment (the platform's view, not its own)",
}


def traditions(result: TraditionsComparison) -> str:
    """F12: each tradition's position, apart from the Marxist assessment of it."""
    parts = [f"## Leftist traditions on: {escape(result.topic)}"]
    named = [
        p.name + (f" ({', '.join(p.tradition.representatives)})" if p.tradition.representatives else "")
        for p in result.perspectives
    ]
    if named:
        parts.append("Traditions (AI-chosen): " + escape("; ".join(named)))
    if result.left_out:
        parts.append("Left out, no material in the library: " + escape(", ".join(result.left_out)))
    if result.status is TraditionsStatus.NO_OTHER_TRADITION:
        parts.append("No other leftist tradition differs materially on this topic (AI judgement).")
        if result.none_reason:
            parts.append(f"Why: {escape(result.none_reason)}")
        parts.append(warnings(result.warnings, result.tokens_used))
        return join(*parts)
    purposes = {}
    for perspective in result.perspectives:
        purposes.update({n: f"{perspective.name}, own words" for n in perspective.own})
        purposes.update({n: f"{perspective.name}, described by others" for n in perspective.reported})
    parts.append(sources(result.sources, result.cited, purposes))
    if result.status is TraditionsStatus.COMPARED:
        parts.append(ai_heading("Comparison, generated from the passages", result.personalized))
        for perspective in result.perspectives:
            rows = []
            for kind, title in _STATEMENT_TITLES.items():
                for statement in result.statements_of(perspective.name, kind):
                    if kind is StatementKind.POSITION and not statement.in_own_words:
                        title = "Position, as others describe it"
                    rows.append(line(f"{title}: {statement.text}", statement.evidence))
            if rows:
                parts.append(f"**{escape(perspective.name)}**\n\n" + "\n".join(rows))
        if result.disagreements:
            parts.append("**Where they disagree**\n\n" + "\n".join(
                line((f"{d.sides}: " if d.sides else "") + d.text, d.evidence) for d in result.disagreements
            ))
        if result.gaps:
            parts.append("**Gaps: what the passages cannot show**\n\n" + "\n".join(line(g) for g in result.gaps))
    if result.perspectives and result.status is not TraditionsStatus.ONE_PERSPECTIVE:
        rows = []
        for perspective in result.perspectives:
            if not perspective.readings:
                rows.append(f"- {escape(perspective.name)}: the library has no text by its representatives")
            for reading in perspective.readings:
                rows.append(f"- {escape(perspective.name)}: {escape(reading.title)} — {escape(reading.author)} "
                            f"({read_link(reading.document_id, reading.start)})")
        parts.append("### Read each tradition in its own words\n\n" + "\n".join(rows))
    parts.append(warnings(result.warnings, result.tokens_used))
    return join(*parts)


_STATUS_LINES = {
    ReadingStatus.UNREAD: "You have not opened it yet.",
    ReadingStatus.COMPLETED: "You have finished it.",
}


def recommendations(result: RecommendationResult) -> str:
    """F07: library texts, best first, each with why."""
    how = "ranked by AI" if result.ranked_by_model else "ranked by matching passages"
    if result.personalized:
        how += ", adapted to your reader profile"
    parts = [f"## Readings on {escape(result.topic)}", f"*{how}*"]
    for number, item in enumerate(result.recommendations, start=1):
        document = item.document
        year = f" ({document.publication_date.year})" if document.publication_date else ""
        difficulty = f" — *{item.difficulty}*" if item.difficulty else ""
        label = "Why (AI-generated): " if result.ranked_by_model else "Why: "
        rows = [f"**{number}. {escape(document.title + year)}** — {escape(document.author)}{difficulty}",
                escape(label + item.reason)]
        if item.status is ReadingStatus.IN_PROGRESS:
            rows.append(f"You have read {item.progress:.0%} of it.")
        elif item.status in _STATUS_LINES:
            rows.append(_STATUS_LINES[item.status])
        start = item.passages[0].locator if item.passages else ""
        rows.append(read_link(document.id, start, "start reading"))
        parts.append("  \n".join(rows))
    if result.external:
        parts.append("### Not in the library (named by the AI, not checked)\n\n" + "\n".join(
            line(f"{s.title}{' — ' + s.author if s.author else ''}: {s.reason}") for s in result.external
        ))
    if not result.recommendations and not result.external:
        parts.append("No readings to recommend.")
    parts.append(warnings(result.warnings, result.tokens_used))
    return join(*parts)


_STEP_MARKS = {StepStatus.DONE: " ✓ done", StepStatus.KNOWN: " ✓ already known", StepStatus.SKIPPED: " — skipped"}


def learning_path(path: LearningPath) -> str:
    """F08: what a topic assumes, in order, with readings."""
    how = "prerequisites identified by AI"
    if path.personalized:
        how += ", checked against your reader profile"
    parts = [f"## Learning path for {escape(path.target)}", f"*{how}*"]
    if path.already_known:
        parts.append("Left out, as you said you know: " + escape(", ".join(path.already_known)))
    if path.no_path_required:
        parts.append("You already know what this assumes, so no path is needed.")
    for number, step in enumerate(path.steps, start=1):
        prerequisite = step.prerequisite
        need = "needed" if step.required else "suggested"
        rows = [f"**{number}. {escape(step.name)}** — {prerequisite.kind}, {need}{_STEP_MARKS.get(step.status, '')}"]
        if prerequisite.why:
            rows.append(escape(f"Why (AI-generated): {prerequisite.why}"))
        if step.note:
            rows.append(escape(step.note))
        for citation in step.readings:
            excerpt = citation.quoted_text
            if len(excerpt) > READING_EXCERPT_CHARS:
                excerpt = excerpt[:READING_EXCERPT_CHARS].rstrip() + " […]"
            rows.append(f"Read: {escape(citation.format())} ({read_link(citation.document_id, citation.locator)})"
                        f"  \n> {escape(excerpt)}")
        if step.is_gap and prerequisite.orientation:
            rows.append(escape("Orientation (AI-generated; nothing in the library on this): "
                               + prerequisite.orientation))
        parts.append("  \n".join(rows))
    if path.steps:
        parts.append(f"*Learning path {str(path.id)[:8]}: record progress with "
                     f"`praxis path mark {str(path.id)[:8]} <step> done|known|skip`.*")
    parts.append(warnings(path.warnings, path.tokens_used))
    return join(*parts)


_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def comparison(result: SourceComparison) -> str:
    """F10: each source's passages, then what the AI found shared,
    different, disputed and framed, each point naming whose passages."""
    letters = {p.document_id: _LETTERS[i] for i, p in enumerate(result.profiles)}
    parts = [f"## Comparing on: {escape(result.subject)}"]
    for profile in result.profiles:
        rows = [f"### Source {letters[profile.document_id]}: {escape(profile.describe())}"]
        for source in result.passages_of(profile):
            text = source.citation.quoted_text
            if len(text) > SHOWN_PASSAGE_CHARS:
                text = text[:SHOWN_PASSAGE_CHARS].rstrip() + " […]"
            rows.append(f"**{escape(source.label)}** {escape(source.citation.locator)} — "
                        f"{read_link(profile.document_id, source.citation.locator)}\n\n> {escape(text)}")
        parts.append("\n\n".join(rows))
    if result.comparability is not Comparability.UNKNOWN:
        note = f" — {result.comparability_note}" if result.comparability_note else ""
        parts.append(f"**Comparability (AI-assessed):** {escape(result.comparability.value + note)}")

    def owners(evidence: tuple[int, ...]) -> str:
        names = dict.fromkeys(
            letters.get(profile.document_id, "?")
            for profile in (result.source_of(n) for n in evidence) if profile is not None
        )
        return f" (source{'s' if len(names) > 1 else ''} {', '.join(names)})" if names else ""

    for title, points in (
        ("Shared ground (AI-generated)", result.similarities),
        ("Differences in treatment (AI-generated)", result.differences),
        ("Factual disagreements (AI-generated; check the passages)", result.disagreements),
        ("Observations on framing (AI interpretation, not established fact)", result.observations),
    ):
        if points:
            parts.append(f"**{title}**\n\n" + "\n".join(
                line((f"{p.aspect}: " if p.aspect else "") + p.description, p.evidence) + escape(owners(p.evidence))
                for p in points
            ))
    if result.uncertainties:
        parts.append("**Could not be verified from these passages**\n\n" + "\n".join(line(u) for u in result.uncertainties))
    parts.append(warnings(result.warnings, result.tokens_used))
    return join(*parts)
