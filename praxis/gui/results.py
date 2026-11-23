"""Each feature's result as rich text for the result panes.

The GUI's counterparts of the CLI's ``_print_answer``, ``_print_research``,
``_print_history`` and so on. Only formatting: what is shown, and how it is
labelled, follows the CLI, so both interfaces say the same things about
what is AI-generated, tentative or unchecked. The look comes from
``praxis.gui.render``: passages in white cards, AI text in tinted boxes,
citations as links to their passages.

Long results open with a "Jump to" bar. Where the model synthesised many
passages (research, history, analysis, comparisons) its findings come
first and the passages follow, each finding linking down to what it
cites; a plain question (F04, "source-first") still shows its passages
before the explanation.
"""

from __future__ import annotations

from praxis.agent import AgentResponse, ResponseStatus
from praxis.comparison import Comparability, SourceComparison
from praxis.gui.render import (
    AI_INK,
    AI_PAPER,
    GOOD,
    MUTED,
    NOTE_PAPER,
    RED,
    RULE,
    ai_box,
    ai_prose,
    badge,
    box,
    bullets,
    cite,
    esc,
    join,
    jump_bar,
    meta,
    passage_card,
    point,
    progress,
    quote,
    read_href,
    read_link,
    section,
    shorten,
    source_anchor,
    sources,
    subsection,
    title,
    warnings,
)
from praxis.news.events import Grouping
from praxis.news.exploration import ExpandedEvent
from praxis.reading import LearningPath, ReadingStatus, RecommendationResult
from praxis.reading.prerequisites import StepStatus
from praxis.reading.traditions import StatementKind, TraditionsComparison, TraditionsStatus
from praxis.research.analysis import AnalysisItemKind, AnalysisStatus, MaterialistAnalysis
from praxis.research.history import ContextStatus, HistoricalContext, HistoryItemKind, SuggestedReading
from praxis.research.result import ResearchResult

READING_EXCERPT_CHARS = 220
STEP_SCHEME = "praxis:step"
PATH_SCHEME = "praxis:path"  # opens a learning path on its page


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count != 1 else ''}"


def _jump(*targets: tuple[str, str, bool]) -> str:
    """The jump bar, listing only the parts that are shown."""
    return jump_bar([(label, anchor) for label, anchor, shown in targets if shown])


def _reading_rows(readings, describe=lambda r: "") -> str:
    rows = []
    for reading in readings:
        start = getattr(reading, "start", "")
        extra = describe(reading)
        rows.append(f"<b>{esc(reading.title)}</b> — {esc(reading.author)}"
                    + (f' <span style="color:{MUTED};">{esc(extra)}</span>' if extra else "")
                    + f" &nbsp;{read_link(reading.document_id, start, 'Read ›')}")
    return bullets(rows)


def answer(response: AgentResponse) -> str:
    """F04: the passages first, then the explanation."""
    explained = response.status is ResponseStatus.ANSWERED and bool(response.explanation)
    return join(
        title(response.question, "A question answered from the library"),
        _jump(("Passages", "sources", bool(response.sources)), ("Explanation", "explanation", explained)),
        warnings(response.warnings),
        sources(response.sources, response.cited, heading="Passages"),
        section("Explanation", ai_prose("Explanation", response.explanation, response.personalized), "explanation")
        if explained else "",
        warnings((), response.tokens_used),
    )


def _research_steps(result: ResearchResult) -> str:
    rows = []
    for step in result.session.steps:
        mark = f'<span style="color:{GOOD};">✓</span>' if step.succeeded else f'<span style="color:{RED};">✗</span>'
        detail = f" (+{len(step.new_sources)} sources)" if step.new_sources else ""
        error = f' <span style="color:{RED};">— {esc(step.error)}</span>' if step.error else ""
        rows.append(f"<li>{mark} {esc(step.description)}"
                    f'<span style="color:{MUTED};">{esc(detail)}</span>{error}</li>')
    body = f'<ol style="color:{MUTED}; font-size:13px; margin-top:0px;">{"".join(rows)}</ol>' if rows else ""
    if result.stop_reason:
        body += f'<p style="color:{MUTED}; font-size:13px;"><i>Stopped: {esc(result.stop_reason.value)}.</i></p>'
    return body


def research(result: ResearchResult) -> str:
    """F03: the analysis and what was established, then the sources and
    readings, then the steps taken."""
    situation = result.situation
    has_situation = situation is not None and situation.has_findings
    analysed = result.status is ResponseStatus.ANSWERED and bool(result.summary)
    readings = result.get_recommended_readings()
    steps = result.session.steps

    situation_html = ""
    if has_situation:
        groups = (
            ("Contradictions", [point(c.description, c.evidence) for c in situation.contradictions]),
            ("Material relations", [point(r.description, r.evidence, r.relation_type.value.capitalize())
                                    for r in situation.relations]),
            ("Historical development", [point(d.description, d.evidence) for d in situation.developments]),
            ("Where the sources disagree", [point(c.description, c.evidence) for c in situation.conflicts]),
        )
        situation_html = ai_box("Concrete situation, each point citing the sources",
                                "".join(subsection(name, rows) for name, rows in groups), anchor="situation")

    return join(
        title(result.objective, meta(
            f"Research session {str(result.session.id)[:8]}",
            _plural(len(result.sources), "source"),
            _plural(len(steps), "step"),
        )),
        _jump(("Analysis", "analysis", analysed), ("Concrete situation", "situation", has_situation),
              ("Open questions", "questions", bool(result.open_questions)),
              ("Sources", "sources", bool(result.sources)), ("Further reading", "reading", bool(readings)),
              ("How it was researched", "steps", bool(steps))),
        warnings(result.warnings),
        section("Analysis", ai_prose("Analysis", result.summary, result.personalized), "analysis") if analysed else "",
        section("What was established", situation_html) if has_situation else "",
        section("Open questions", ai_box("Open questions", bullets([esc(q) for q in result.open_questions])),
                "questions") if result.open_questions else "",
        sources(result.sources, result.cited, result.purposes),
        section("Further reading", _reading_rows(readings), "reading"),
        section("How it was researched", _research_steps(result), "steps"),
        warnings((), result.session.tokens_used),
    )


def _readings(heading: str, readings: tuple[SuggestedReading, ...]) -> str:
    return section(heading, _reading_rows(
        readings, lambda r: f"cited {r.cited} time{'s' if r.cited != 1 else ''}"), "reading")


def _timeline(items) -> str:
    """Dated items as a two-column table: when, and what happened."""
    rows = []
    for item in items:
        turning = badge("TURNING POINT", AI_PAPER, RED) + " " if item.kind is HistoryItemKind.TURNING_POINT else ""
        rows.append(f'<tr><td width="130" style="color:{RED}; font-weight:700; padding-right:10px;">'
                    f"{esc(item.when)}</td><td>{turning}{esc(item.text)} {cite(item.evidence)}</td></tr>")
    if not rows:
        return ""
    return f'<h4>Chronology</h4><table cellspacing="0" cellpadding="4" width="100%">{"".join(rows)}</table>'


def history(context: HistoricalContext) -> str:
    """F09: origins, a dated chronology, continuities, disputed views, gaps."""
    if context.status is ContextStatus.TOO_BROAD:
        return join(
            title(context.topic, "Too broad to trace well from a few library passages"),
            ai_box("Narrower topics to try", bullets([esc(t) for t in context.narrower])),
            "<p>Or tick <b>Trace even if broad</b> and run it again.</p>",
            warnings(context.warnings, context.tokens_used),
        )
    explained = context.status is ContextStatus.EXPLAINED
    body = ""
    if explained:
        if context.overview:
            body += f"<p>{esc(context.overview)} {cite(context.overview_evidence)}</p>"
        body += subsection("Origins", [point(i.text, i.evidence) for i in context.of_kind(HistoryItemKind.ORIGIN)])
        body += _timeline([i for i in context.items if i.kind.is_dated])
        body += subsection("Continuities",
                           [point(i.text, i.evidence) for i in context.of_kind(HistoryItemKind.CONTINUITY)])
        body += subsection("Disputed interpretations (interpretation, not established fact)",
                           [point(i.text, i.evidence) for i in context.of_kind(HistoryItemKind.INTERPRETATION)])
        body += subsection("Gaps: what the passages do not cover", [esc(g) for g in context.gaps])
    return join(
        title(f"Historical context: {context.topic}"),
        _jump(("How it developed", "account", explained), ("Sources", "sources", bool(context.sources)),
              ("Read further", "reading", explained and bool(context.readings))),
        warnings(context.warnings),
        section("How it developed",
                ai_box("How it developed, organised from the passages", body, context.personalized),
                "account") if explained else "",
        sources(context.sources, context.cited, context.purposes),
        _readings("Read further", context.readings) if explained else "",
        warnings((), context.tokens_used),
    )


_CLAIM_BADGES = {
    "supported": badge("SUPPORTED BY SEVERAL PASSAGES", "#dfe9d8", GOOD),
    "tentative": badge("TENTATIVE", NOTE_PAPER, MUTED),
}


def analysis(result: MaterialistAnalysis) -> str:
    """F11: conditions, theory applied to evidence, claims marked supported
    or tentative, other readings and limits."""
    analysed = result.status is AnalysisStatus.ANALYSED
    body = ""
    if analysed:
        for kind, heading in (
            (AnalysisItemKind.CONDITION, "What the evidence shows"),
            (AnalysisItemKind.APPLICATION, "Theory applied to the evidence"),
            (AnalysisItemKind.CLAIM, "Interpretations"),
            (AnalysisItemKind.ALTERNATIVE, "Other readings within Marxist analysis"),
        ):
            rows = []
            for item in result.of_kind(kind):
                if kind is AnalysisItemKind.CLAIM:
                    rows.append(f"{_CLAIM_BADGES.get(item.label, '')} {point(item.text, item.evidence)}")
                else:
                    rows.append(point(item.text, item.evidence, item.label))
            body += subsection(heading, rows)
        body += subsection("Limits: where the theory may not fit or the evidence is thin",
                           [esc(limit) for limit in result.limits])
    concepts = " ".join(badge(c.name) for c in result.concepts)
    details = []
    if result.framework:
        details.append(f"Framework requested: <b>{esc(result.framework)}</b>")
    if concepts:
        details.append(f"Concepts applied (AI-chosen): {concepts}")
    return join(
        title(f"Marxist analysis: {result.issue}"),
        "".join(f'<p style="font-size:13px;">{d}</p>' for d in details),
        _jump(("Analysis", "analysis", analysed), ("Sources", "sources", bool(result.sources)),
              ("Theory to study", "reading", analysed and bool(result.readings))),
        warnings(result.warnings),
        section("Analysis", ai_box("Analysis, an interpretation", body, result.personalized), "analysis")
        if analysed else "",
        sources(result.sources, result.cited, result.purposes),
        _readings("Theory to study further", result.readings) if analysed else "",
        warnings((), result.tokens_used),
    )


_STATEMENT_TITLES = {
    StatementKind.POSITION: "Position",
    StatementKind.CONDITIONS: "Conditions it developed in",
    StatementKind.ASSESSMENT: "Marxist assessment (the platform's view, not its own)",
}


def traditions(result: TraditionsComparison) -> str:
    """F12: each tradition's position, apart from the Marxist assessment of it."""
    named = [
        p.name + (f" ({', '.join(p.tradition.representatives)})" if p.tradition.representatives else "")
        for p in result.perspectives
    ]
    head = [title(f"Leftist traditions on: {result.topic}")]
    if named:
        head.append(f'<p style="font-size:13px;">Traditions (AI-chosen): '
                    f'{" ".join(badge(n) for n in named)}</p>')
    if result.left_out:
        head.append(meta("Left out, no material in the library: " + esc(", ".join(result.left_out))))
    if result.status is TraditionsStatus.NO_OTHER_TRADITION:
        why = f"<p>Why: {esc(result.none_reason)}</p>" if result.none_reason else ""
        return join(*head, ai_box("No other leftist tradition differs materially on this topic",
                                  why or "<p>(AI judgement)</p>"),
                    warnings(result.warnings, result.tokens_used))

    purposes = {}
    for perspective in result.perspectives:
        purposes.update({n: f"{perspective.name}, own words" for n in perspective.own})
        purposes.update({n: f"{perspective.name}, described by others" for n in perspective.reported})
    compared = result.status is TraditionsStatus.COMPARED
    cards = ""
    if compared:
        for perspective in result.perspectives:
            rows = ""
            for kind, heading in _STATEMENT_TITLES.items():
                for statement in result.statements_of(perspective.name, kind):
                    label = heading
                    if kind is StatementKind.POSITION and not statement.in_own_words:
                        label = "Position, as others describe it"
                    tint = f' style="color:{AI_INK};"' if kind is StatementKind.ASSESSMENT else ""
                    rows += (f'<p{tint}><b>{esc(label)}:</b> {esc(statement.text)} '
                             f"{cite(statement.evidence)}</p>")
            if rows:
                cards += box(f'<h4 style="margin-top:0px;">{esc(perspective.name)}</h4>{rows}')
        cards += subsection("Where they disagree", [
            point(d.text, d.evidence, d.sides) for d in result.disagreements])
        cards += subsection("Gaps: what the passages cannot show", [esc(g) for g in result.gaps])
    own_words = ""
    if result.perspectives and result.status is not TraditionsStatus.ONE_PERSPECTIVE:
        rows = []
        for perspective in result.perspectives:
            if not perspective.readings:
                rows.append(f"<b>{esc(perspective.name)}</b>: "
                            f'<span style="color:{MUTED};">the library has no text by its representatives</span>')
            for reading in perspective.readings:
                rows.append(f"<b>{esc(perspective.name)}</b>: {esc(reading.title)} — {esc(reading.author)} "
                            f"&nbsp;{read_link(reading.document_id, reading.start, 'Read ›')}")
        own_words = section("Read each tradition in its own words", bullets(rows), "reading")
    return join(
        *head,
        _jump(("Comparison", "comparison", compared), ("Sources", "sources", bool(result.sources)),
              ("Own words", "reading", bool(own_words))),
        warnings(result.warnings),
        section("Comparison", ai_box("Comparison, generated from the passages", cards, result.personalized),
                "comparison") if compared else "",
        sources(result.sources, result.cited, purposes),
        own_words,
        warnings((), result.tokens_used),
    )


_STATUS_BADGES = {
    ReadingStatus.UNREAD: badge("NOT OPENED YET"),
    ReadingStatus.COMPLETED: badge("FINISHED", "#dfe9d8", GOOD),
}


def recommendations(result: RecommendationResult) -> str:
    """F07: library texts, best first, each with why."""
    how = "Ranked by AI" if result.ranked_by_model else "Ranked by matching passages"
    if result.personalized:
        how += ", adapted to your reader profile"
    cards = []
    for number, item in enumerate(result.recommendations, start=1):
        document = item.document
        year = f" ({document.publication_date.year})" if document.publication_date else ""
        tags = []
        if item.difficulty:
            tags.append(badge(item.difficulty.upper()))
        if item.status is ReadingStatus.IN_PROGRESS:
            tags.append(badge(f"{item.progress:.0%} READ", AI_PAPER, AI_INK))
        elif item.status in _STATUS_BADGES:
            tags.append(_STATUS_BADGES[item.status])
        why_label = (f"{badge('AI', AI_PAPER, AI_INK)} <b>Why:</b>" if result.ranked_by_model else "<b>Why:</b>")
        start = item.passages[0].locator if item.passages else ""
        bar = progress(item.progress, 40) if item.status is ReadingStatus.IN_PROGRESS else ""
        cards.append(box(
            f'<p style="font-size:16px; margin-bottom:2px;"><span style="color:{RED}; font-weight:800;">'
            f"{number}.</span> <b>{esc(document.title + year)}</b></p>"
            f'<p style="color:{MUTED};">{esc(document.author)} &nbsp;{" ".join(tags)}</p>'
            f"{bar}<p>{why_label} {esc(item.reason)}</p>"
            f'<p style="margin-bottom:0px;"><a href="{read_href(document.id, start)}"><b>Start reading ›</b></a></p>'
        ))
    external = ""
    if result.external:
        external = section("Not in the library", ai_box("Named by the AI, not checked", bullets([
            point(s.reason, (), s.title + (f" — {s.author}" if s.author else "")) for s in result.external
        ])))
    empty = "" if cards or external else "<p>No readings to recommend.</p>"
    return join(
        title(f"Readings on {result.topic}", how),
        warnings(result.warnings),
        "".join(cards), external, empty,
        warnings((), result.tokens_used),
    )


_STEP_BADGES = {
    StepStatus.DONE: badge("✓ DONE", "#dfe9d8", GOOD),
    StepStatus.KNOWN: badge("✓ ALREADY KNOWN", "#dfe9d8", GOOD),
    StepStatus.SKIPPED: badge("SKIPPED"),
}
_STEP_ACTIONS = (
    (StepStatus.DONE, "✓ Mark done"),
    (StepStatus.KNOWN, "I already know this"),
    (StepStatus.SKIPPED, "Skip"),
)


def step_href(number: int, status: StepStatus) -> str:
    return f"{STEP_SCHEME}/{number}/{status.name.lower()}"


def parse_step_link(url: str) -> tuple[int, StepStatus] | None:
    """(step number, status) from a step action link, else None."""
    if not url.startswith(STEP_SCHEME + "/"):
        return None
    number, _, status = url[len(STEP_SCHEME) + 1:].partition("/")
    try:
        return int(number), StepStatus[status.upper()]
    except (ValueError, KeyError):
        return None


def _step_actions(number: int, status: StepStatus) -> str:
    if status is StepStatus.TODO:
        links = [f'<a href="{step_href(number, s)}"><b>{esc(label)}</b></a>' for s, label in _STEP_ACTIONS]
    else:
        links = [f'<a href="{step_href(number, StepStatus.TODO)}">Undo</a>']
    return f'<p style="margin-top:8px; margin-bottom:0px;">{" &nbsp;&nbsp;·&nbsp;&nbsp; ".join(links)}</p>'


def learning_path(path: LearningPath, interactive: bool = False) -> str:
    """F08: what a topic assumes, in order, with readings. Settled steps
    fold to one line. ``interactive`` adds links to mark each step."""
    how = "Prerequisites identified by AI"
    if path.personalized:
        how += ", checked against your reader profile"
    total = len(path.steps)
    head = [title(f"Learning path: {path.target}", how)]
    if total:
        settled = path.settled_count
        upcoming = path.next_step
        next_line = (f" &nbsp;·&nbsp; Next: <b>step {upcoming[0]}, {esc(upcoming[1].name)}</b>"
                     if upcoming else " &nbsp;·&nbsp; <b>All steps dealt with.</b>")
        head.append(f'<p style="margin-bottom:0px;">{settled} of {total} steps dealt with{next_line}</p>'
                    + progress(settled / total))
    if path.already_known:
        head.append(meta("Left out, as you said you know: " + esc(", ".join(path.already_known))))
    if path.no_path_required:
        head.append("<p>You already know what this assumes, so no path is needed.</p>")

    cards = []
    for number, step in enumerate(path.steps, start=1):
        prerequisite = step.prerequisite
        settled = step.status is not StepStatus.TODO
        need = badge("ESSENTIAL", AI_PAPER, RED) if step.required else badge("SUGGESTED")
        header = (f'<p style="font-size:16px; margin-bottom:4px;"><span style="color:{RED}; font-weight:800;">'
                  f"{number}.</span> <b>{esc(step.name)}</b> &nbsp;{badge(prerequisite.kind.upper())} {need} "
                  f"{_STEP_BADGES.get(step.status, '')}</p>")
        body = ""
        if not settled:
            if prerequisite.why:
                body += (f'<p style="color:{AI_INK};">{badge("AI", AI_PAPER, AI_INK)} '
                         f"<b>Why it matters:</b> {esc(prerequisite.why)}</p>")
            if step.note:
                body += f'<p style="color:{MUTED};">{esc(step.note)}</p>'
            for citation in step.readings:
                body += (f'<p style="margin-top:8px; margin-bottom:2px;"><b>Read:</b> '
                         f"{esc(citation.author)}, <i>{esc(citation.document_title)}</i> "
                         f'<span style="color:{MUTED};">{esc(citation.locator)}</span> &nbsp;'
                         f"{read_link(citation.document_id, citation.locator, 'Open ›')}</p>"
                         + quote(shorten(citation.quoted_text, READING_EXCERPT_CHARS)))
            if step.is_gap and prerequisite.orientation:
                body += ai_box("Orientation — nothing in the library on this", f"<p>{esc(prerequisite.orientation)}</p>")
        if interactive:
            body += _step_actions(number, step.status)
        background = NOTE_PAPER if settled else None
        cards.append(box(header + body, background or "#fffdf8", RULE, 12,
                         MUTED if settled else "#1a1a1a", anchor=f"step-{number}"))
    footer = ""
    if total and not interactive:
        footer = (f'<p style="margin-top:6px;"><a href="{PATH_SCHEME}/{path.id}"><b>Track your progress '
                  f"on the Learning paths page ›</b></a></p>")
    return join(*head, warnings(path.warnings), "".join(cards), footer, warnings((), path.tokens_used))


_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def comparison(result: SourceComparison) -> str:
    """F10: what the AI found shared, different, disputed and framed, each
    point naming whose passages; then each source's passages."""
    letters = {p.document_id: _LETTERS[i] for i, p in enumerate(result.profiles)}

    def letter_badge(letter: str) -> str:
        return badge(letter, RED, "#fbf7ee")

    def owners(evidence: tuple[int, ...]) -> str:
        names = dict.fromkeys(
            letters.get(profile.document_id, "?")
            for profile in (result.source_of(n) for n in evidence) if profile is not None
        )
        return " ".join(letter_badge(n) for n in names)

    def source_name(profile) -> str:
        return f'<b style="color:{RED};">Source {letters[profile.document_id]}:</b> {esc(profile.describe())}'

    legend = bullets([source_name(p) for p in result.profiles])
    findings = ""
    if result.comparability is not Comparability.UNKNOWN:
        note = f" — {esc(result.comparability_note)}" if result.comparability_note else ""
        findings += f"<p><b>Comparability (AI-assessed):</b> {esc(result.comparability.value)}{note}</p>"
    for heading, points in (
        ("Shared ground", result.similarities),
        ("Differences in treatment", result.differences),
        ("Factual disagreements (check the passages)", result.disagreements),
        ("Observations on framing (interpretation, not established fact)", result.observations),
    ):
        findings += subsection(heading, [
            f"{owners(p.evidence)} {point(p.description, p.evidence, p.aspect)}" for p in points
        ])
    findings += subsection("Could not be verified from these passages", [esc(u) for u in result.uncertainties])

    passages = ""
    for profile in result.profiles:
        cards = "".join(passage_card(source) for source in result.passages_of(profile))
        passages += f"<h4>{source_name(profile)}</h4>{cards}"
    return join(
        title(f"Comparing on: {result.subject}"),
        legend,
        _jump(("Findings", "findings", bool(findings)), ("Passages", "sources", bool(passages))),
        warnings(result.warnings),
        section("Findings", ai_box("Comparison of the passages", findings), "findings") if findings else "",
        section("Each source's passages", passages, "sources"),
        warnings((), result.tokens_used),
    )


def _report_card(source, report) -> str:
    when = report.publication_date.isoformat() if report.publication_date else "undated"
    head = (f'<p style="margin-bottom:4px;"><span style="color:{RED}; font-weight:800;">{esc(source.label)}</span> '
            f'<b>{esc(report.outlet)}</b><span style="color:{MUTED};"> · {esc(when)}</span></p>'
            f'<p style="font-size:15px; font-weight:700;">{esc(report.title)}</p>')
    body = quote(source.citation.quoted_text) if source.citation.quoted_text != report.title else ""
    link = (f'<p style="font-size:13px; margin-bottom:0px;"><a href="{esc(report.source_url)}">'
            f"Read the full report at {esc(report.outlet)} ↗</a></p>") if report.source_url else ""
    return box(head + body + link, anchor=source_anchor(source.number))


def expanded_event(expanded: ExpandedEvent) -> str:
    """F02: an AI account of the event, then the reports and background
    passages it draws on, and reports that may be related."""
    event = expanded.event
    details = []
    if event.first_date and event.last_date and event.first_date != event.last_date:
        details.append(f"{event.first_date:%b %d} – {event.last_date:%b %d, %Y}")
    elif event.last_date:
        details.append(f"{event.last_date:%b %d, %Y}")
    details += [esc(c) for c in event.categories]
    details.append(_plural(len(event.outlets), "outlet"))
    flags = []
    if expanded.developing:
        flags.append("<b>Still developing:</b> the reports are recent and may change.")
    if event.grouping is Grouping.UNCERTAIN:
        flags.append("<b>Grouping uncertain:</b> these reports may not all be about one event.")
    if event.note:
        flags.append(esc(event.note))
    flag_box = box("".join(f'<p style="margin-bottom:2px;">{f}</p>' for f in flags), NOTE_PAPER, RULE, 10) if flags else ""
    reports = "".join(_report_card(s, r) for s, r in zip(expanded.report_sources, event.reports))
    related = ""
    if expanded.related:
        related = section("Other reports that may be related", bullets([
            f"<b>{esc(r.outlet)}</b>: {esc(r.title)}" for r in expanded.related
        ]), "related", "not grouped with this event")
    return join(
        f"<h2>{esc(event.headline)}</h2>", meta(*details), flag_box,
        _jump(("Account", "account", bool(expanded.account)), ("Reports", "reports", bool(reports)),
              ("Background", "sources", bool(expanded.library_sources)), ("Related", "related", bool(related))),
        warnings(expanded.warnings),
        section("Account of the event", ai_prose("Account of the event", expanded.account), "account")
        if expanded.account else "",
        section("Open questions", ai_box("Open questions", bullets([esc(q) for q in expanded.open_questions])))
        if expanded.open_questions else "",
        section("Reports", reports, "reports", _plural(len(event.reports), "report")),
        sources(expanded.library_sources, expanded.cited, heading="Background from the library"),
        related,
        warnings((), expanded.tokens_used),
    )
