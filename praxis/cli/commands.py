"""Command-line interface.

Each command is a thin controller: it parses arguments, calls a service from
the shared ``Application``, and prints the result. No business logic here.

Python notes: Typer reads each function's parameters and type hints to build
the command's arguments and options, so the signatures below *are* the CLI.
``with session() as application:`` opens the application, runs the block,
and always closes it again, even when the block fails (like Go's ``defer``).
"""

from __future__ import annotations

import textwrap
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn, Optional

import typer

from praxis.agent import AgentError, AgentResponse, ResponseStatus, Source
from praxis.app import Application, build_application, bundled_library_service
from praxis.comparison import Comparability, SourceComparison, SourceSelection
from praxis.documents import Annotation, AnnotationType, Document
from praxis.library import LibraryError, SourceReference
from praxis.news import NewsProviderError
from praxis.news.service import NewsRefresh
from praxis.reader_model import ExplanationDepth, KnowledgeLevel, ReaderProfile
from praxis.reader_model.events import DocumentRead
from praxis.reading import AnnotationError, AnnotationResult
from praxis.research import ResearchBudget, ResearchError
from praxis.research.result import ResearchResult
from praxis.research.situation import ConcreteSituation
from praxis.workspace import SavedItem, SavedItemKind

app = typer.Typer(help="Praxis: Marxist political research and learning.", no_args_is_help=True)
library_app = typer.Typer(help="Browse, search and read the text library (F05).", no_args_is_help=True)
profile_app = typer.Typer(help="Inspect and correct your reader model (F13).", no_args_is_help=True)
workspace_app = typer.Typer(help="Save and return to texts, passages and notes (F15).", no_args_is_help=True)
sessions_app = typer.Typer(help="Reopen and continue earlier research (F03).", no_args_is_help=True)
annotations_app = typer.Typer(help="List and remove the AI annotations on a text (F06).", no_args_is_help=True)
news_app = typer.Typer(help="Current news from the configured feeds (F01).", no_args_is_help=True)
comparisons_app = typer.Typer(help="Reopen earlier source comparisons (F10).", no_args_is_help=True)
app.add_typer(library_app, name="library")
app.add_typer(profile_app, name="profile")
app.add_typer(workspace_app, name="workspace")
app.add_typer(sessions_app, name="sessions")
app.add_typer(annotations_app, name="annotations")
app.add_typer(comparisons_app, name="comparisons")
app.add_typer(news_app, name="news")

# Tests replace this to run commands against an in-memory database.
application_factory = build_application

# Errors whose message is meant for the user, not a stack trace.
USER_ERRORS = (AgentError, AnnotationError, LibraryError, NewsProviderError, ResearchError, ValueError)

# Longest stretch of a passage printed by `ask`; the rest is one command away.
SHOWN_PASSAGE_CHARS = 600


def _fail(message: str) -> NoReturn:
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


@contextmanager
def session() -> Iterator[Application]:
    application = application_factory()
    try:
        yield application
    except USER_ERRORS as exc:
        _fail(str(exc))
    finally:
        application.close()


def _short_id(document: Document) -> str:
    return str(document.id)[:8]


def _print_documents(documents: list[Document], empty_message: str) -> None:
    if not documents:
        typer.echo(empty_message)
        return
    for document in documents:
        year = f" ({document.publication_date.year})" if document.publication_date else ""
        typer.echo(f"{_short_id(document)}  {document.title}{year} — {document.author}")
        if document.topics:
            typer.echo(f"          topics: {', '.join(document.topics)}")


# --- questions (F04) ---------------------------------------------------------


@app.command("ask")
def ask(
    question: Annotated[str, typer.Argument(help="Your question, in quotes.")],
    save: Annotated[bool, typer.Option("--save", help="Save the answer to your workspace.")] = False,
    tag: Annotated[Optional[list[str]], typer.Option("--tag", "-t", help="Tag for the saved answer; repeatable.")] = None,
) -> None:
    """Ask a question; get the library passages that address it, then an explanation."""
    with session() as application:
        response = application.agent.answer_question(question)
        saved = None
        if save and response.sources:
            saved = application.workspace.save_answer(response, tags=tuple(tag or ()))
    _print_response(response)
    if saved:
        typer.echo(f"Saved to your workspace [{str(saved.id)[:8]}]")
    elif save:
        typer.echo("Nothing was saved: there were no sources to keep.")


def _print_response(response: AgentResponse) -> None:
    _print_sources(response.sources, response.cited)
    if response.status is ResponseStatus.ANSWERED and response.explanation:
        _print_ai_text("Explanation", response.explanation, response.personalized)
    _print_warnings(response.warnings, response.tokens_used)


def _print_sources(
    sources: tuple[Source, ...],
    cited: tuple[Source, ...],
    purposes: dict[int, str] | None = None,
) -> None:
    cited_numbers = {source.number for source in cited}
    if sources:
        typer.secho("Sources", bold=True)
    for source in sources:
        marker = f"  ({purposes[source.number]})" if purposes and source.number in purposes else ""
        marker += "  (cited)" if source.number in cited_numbers else ""
        typer.secho(f"\n{source.label} {source.citation.format()}{marker}", fg=typer.colors.CYAN)
        text = source.citation.quoted_text
        if len(text) > SHOWN_PASSAGE_CHARS:
            text = text[:SHOWN_PASSAGE_CHARS].rstrip() + " […]"
        typer.echo(textwrap.indent(textwrap.fill(text, width=84), "    "))
        paragraph = source.citation.locator.lstrip("¶")
        typer.echo(
            f"    → praxis library read {str(source.citation.document_id)[:8]} --start {paragraph}"
        )


def _print_ai_text(title: str, text: str, personalized: bool) -> None:
    label = f"{title} (AI-generated"
    label += ", adapted to your reader profile)" if personalized else ")"
    typer.secho(f"\n{label}", bold=True)
    for paragraph in text.split("\n\n"):
        if paragraph.lstrip().startswith("#"):
            # A markdown heading line, then the paragraph under it.
            heading, _, rest = paragraph.partition("\n")
            typer.secho(heading.lstrip("# ").strip(), underline=True)
            paragraph = rest
        if paragraph.strip():
            typer.echo(textwrap.fill(paragraph, width=88))
        typer.echo()


def _print_warnings(warnings: tuple[str, ...], tokens_used: int) -> None:
    for warning in warnings:
        typer.secho(f"Note: {warning}", fg=typer.colors.YELLOW)
    if tokens_used:
        typer.echo(f"({tokens_used} model tokens)")


# --- research (F03) ----------------------------------------------------------


MaxSteps = Annotated[int, typer.Option(min=1, max=20, help="Most search steps to run (assessments are not counted).")]
MaxToolCalls = Annotated[int, typer.Option(min=1, max=40, help="Most library searches to make.")]


@app.command("research")
def research(
    objective: Annotated[str, typer.Argument(help="Your research question, in quotes.")],
    max_steps: MaxSteps = ResearchBudget().max_iterations,
    max_tool_calls: MaxToolCalls = ResearchBudget().max_tool_calls,
    save: Annotated[bool, typer.Option("--save", help="Save the result to your workspace.")] = False,
    tag: Annotated[Optional[list[str]], typer.Option("--tag", "-t", help="Tag for the saved result; repeatable.")] = None,
) -> None:
    """Research a question in several steps: plan, gather sources, then analyse them."""
    budget = ResearchBudget(max_iterations=max_steps, max_tool_calls=max_tool_calls)
    with session() as application:
        result = application.agent.research(objective, budget)
        saved = _save_research(application, result, save, tag)
    _print_research(result)
    _print_continue_hint(result)
    _print_saved(saved, save)


def _save_research(
    application: Application, result: ResearchResult, save: bool, tag: list[str] | None
) -> SavedItem | None:
    if save and result.sources:
        return application.workspace.save_research(result, tags=tuple(tag or ()))
    return None


def _print_saved(saved: SavedItem | None, requested: bool) -> None:
    if saved:
        typer.echo(f"Saved to your workspace [{str(saved.id)[:8]}]")
    elif requested:
        typer.echo("Nothing was saved: there were no sources to keep.")


def _print_continue_hint(result: ResearchResult) -> None:
    short = str(result.session.id)[:8]
    if any(w.startswith("The research could not be saved") for w in result.warnings):
        return
    typer.echo(f"Research session {short}.")
    if result.unfinished_steps:
        typer.echo(f"  Run the remaining steps:  praxis sessions continue {short}")
    typer.echo(f'  Follow up:                praxis sessions continue {short} --focus "..."')


def _print_research(result: ResearchResult) -> None:
    typer.secho("Research steps", bold=True)
    rounds = result.session.rounds
    shown_round = 0
    for number, step in enumerate(result.session.steps, start=1):
        if rounds > 1 and step.round != shown_round:
            shown_round = step.round
            focus = result.session.focuses.get(step.round)
            typer.secho(f"  Round {step.round}" + (f": {focus}" if focus else ""), underline=True)
        mark = "✓" if step.succeeded else "✗"
        if step.is_assessment:
            mark += " ◆"
        detail = f"  +{len(step.new_sources)} sources" if step.new_sources else ""
        if step.retry_of is not None:
            detail += f"  (retry of step {step.retry_of + 1})"
        if step.error:
            detail += f"  — {step.error}"
        typer.echo(f"  {number}. {mark} {step.description}{detail}")
    if result.stop_reason:
        typer.echo(f"  Stopped: {result.stop_reason.value}.")
    typer.echo()

    _print_sources(result.sources, result.cited, result.purposes)
    if result.situation is not None and result.situation.has_findings:
        _print_situation(result.situation)
    if result.status is ResponseStatus.ANSWERED and result.summary:
        _print_ai_text("Analysis", result.summary, result.personalized)
    if result.open_questions:
        typer.secho("Open questions (AI-generated)", bold=True)
        for question in result.open_questions:
            typer.echo(textwrap.fill(question, width=86, initial_indent="  - ", subsequent_indent="    "))
        typer.echo()
    readings = result.get_recommended_readings()
    if readings:
        typer.secho("Further reading", bold=True)
        for reading in readings:
            typer.echo(f"  {str(reading.document_id)[:8]}  {reading.title} — {reading.author}")
        typer.echo()
    _print_warnings(result.warnings, result.session.tokens_used)


def _print_situation(situation: ConcreteSituation) -> None:
    """What the assessments established, each point with its sources."""

    def marks(evidence: tuple[int, ...]) -> str:
        return " [" + ", ".join(map(str, evidence)) + "]"

    sections = [
        ("Contradictions", [c.description + marks(c.evidence) for c in situation.contradictions]),
        ("Material relations", [f"({r.relation_type.value}) {r.description}{marks(r.evidence)}"
                                for r in situation.relations]),
        ("Historical development", [d.description + marks(d.evidence) for d in situation.developments]),
        ("Where the sources disagree", [c.description + marks(c.evidence) for c in situation.conflicts]),
    ]
    typer.secho("\nConcrete situation (AI-assessed; each point cites the sources above)", bold=True)
    for title, lines in sections:
        if lines:
            typer.secho(f"  {title}", underline=True)
            for line in lines:
                typer.echo(textwrap.fill(line, width=86, initial_indent="  - ", subsequent_indent="    "))
    typer.echo()


# --- research sessions (F03, UC15) ------------------------------------------


@sessions_app.command("list")
def sessions_list(
    limit: Annotated[int, typer.Option(min=1, max=200, help="How many sessions to show.")] = 20,
) -> None:
    """List stored research sessions, most recent first."""
    with session() as application:
        summaries = application.agent.list_research(limit)
    if not summaries:
        typer.echo('No research yet. Start with: praxis research "your question"')
        return
    for summary in summaries:
        state = "incomplete" if summary.incomplete else "complete"
        rounds = f", {summary.rounds} rounds" if summary.rounds > 1 else ""
        when = summary.updated_at.astimezone().strftime("%Y-%m-%d %H:%M")
        typer.echo(f"{str(summary.id)[:8]}  {when}  {summary.objective}")
        typer.echo(f"          {state}, {summary.source_count} sources{rounds}")


@sessions_app.command("show")
def sessions_show(
    session_id: Annotated[str, typer.Argument(help="Session id or prefix.")],
) -> None:
    """Show a stored research session as it was last left."""
    with session() as application:
        agent = application.agent
        result = agent.get_research(agent.find_research(session_id))
    if result.is_incomplete:
        typer.secho("This research is incomplete.", fg=typer.colors.YELLOW)
    _print_research(result)
    _print_continue_hint(result)


@sessions_app.command("compare")
def sessions_compare(
    session_id: Annotated[str, typer.Argument(help="Session id or prefix.")],
    save: Annotated[bool, typer.Option("--save", help="Save the comparison to your workspace.")] = False,
    tag: Annotated[Optional[list[str]], typer.Option("--tag", "-t", help="Tag for the saved comparison; repeatable.")] = None,
) -> None:
    """Compare how the texts behind a research session treat its question."""
    with session() as application:
        agent = application.agent
        comparison = agent.compare_research_sources(agent.find_research(session_id))
        saved = _save_comparison(application, comparison, save, tag)
    _print_comparison(comparison)
    _print_comparison_hint(comparison)
    _print_saved(saved, save)


@sessions_app.command("continue")
def sessions_continue(
    session_id: Annotated[str, typer.Argument(help="Session id or prefix.")],
    focus: Annotated[Optional[str], typer.Option("--focus", "-f", help="What to follow up on, in quotes.")] = None,
    max_steps: MaxSteps = ResearchBudget().max_iterations,
    max_tool_calls: MaxToolCalls = ResearchBudget().max_tool_calls,
    save: Annotated[bool, typer.Option("--save", help="Save the result to your workspace.")] = False,
    tag: Annotated[Optional[list[str]], typer.Option("--tag", "-t", help="Tag for the saved result; repeatable.")] = None,
) -> None:
    """Run another round of earlier research: a new direction, or the steps left unrun."""
    budget = ResearchBudget(max_iterations=max_steps, max_tool_calls=max_tool_calls)
    with session() as application:
        agent = application.agent
        result = agent.continue_research(agent.find_research(session_id), focus, budget)
        saved = _save_research(application, result, save, tag)
    _print_research(result)
    _print_continue_hint(result)
    _print_saved(saved, save)


# --- source comparison (F10) -------------------------------------------------

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@app.command("compare")
def compare(
    sources: Annotated[list[str], typer.Argument(help="Two to four texts: an id or prefix, optionally with paragraphs, e.g. 3f2a91c0:12-14 or 3f2a91c0:5,9.")],
    on: Annotated[str, typer.Option("--on", help="What to compare them on, in quotes. Needed unless every source names paragraphs.")] = "",
    save: Annotated[bool, typer.Option("--save", help="Save the comparison to your workspace.")] = False,
    tag: Annotated[Optional[list[str]], typer.Option("--tag", "-t", help="Tag for the saved comparison; repeatable.")] = None,
) -> None:
    """Compare how sources treat a subject: shared ground, framing, and factual disagreements."""
    with session() as application:
        chosen = [_parse_source(application, spec) for spec in sources]
        comparison = application.agent.compare_sources(chosen, on)
        saved = _save_comparison(application, comparison, save, tag)
    _print_comparison(comparison)
    _print_comparison_hint(comparison)
    _print_saved(saved, save)


def _save_comparison(
    application: Application, comparison: SourceComparison, save: bool, tag: list[str] | None
) -> SavedItem | None:
    if save and len(comparison.profiles) >= 2:
        return application.workspace.save_comparison(comparison, tags=tuple(tag or ()))
    return None


def _print_comparison_hint(comparison: SourceComparison) -> None:
    if len(comparison.profiles) < 2 or any(w.startswith("The comparison could not be stored") for w in comparison.warnings):
        return
    typer.echo(f"Comparison {str(comparison.id)[:8]}.  Reopen: praxis comparisons show {str(comparison.id)[:8]}")


@comparisons_app.command("list")
def comparisons_list(
    limit: Annotated[int, typer.Option(min=1, max=200, help="How many comparisons to show.")] = 20,
) -> None:
    """List stored comparisons, newest first."""
    with session() as application:
        summaries = application.agent.list_comparisons(limit)
    if not summaries:
        typer.echo('No comparisons yet. Start with: praxis compare <id> <id> --on "subject"')
        return
    for summary in summaries:
        when = summary.created_at.astimezone().strftime("%Y-%m-%d %H:%M")
        typer.echo(f"{str(summary.id)[:8]}  {when}  on {summary.subject}")
        typer.echo(f"          {' / '.join(summary.titles)} ({summary.comparability.value})")


@comparisons_app.command("show")
def comparisons_show(
    comparison_id: Annotated[str, typer.Argument(help="Comparison id or prefix.")],
    save: Annotated[bool, typer.Option("--save", help="Save the comparison to your workspace.")] = False,
    tag: Annotated[Optional[list[str]], typer.Option("--tag", "-t", help="Tag for the saved comparison; repeatable.")] = None,
) -> None:
    """Show a stored comparison as it was made."""
    with session() as application:
        agent = application.agent
        comparison = agent.get_comparison(agent.find_comparison(comparison_id))
        saved = _save_comparison(application, comparison, save, tag)
    _print_comparison(comparison)
    _print_saved(saved, save)


def _parse_source(application: Application, spec: str) -> SourceSelection:
    """``3f2a91c0``, ``3f2a91c0:12``, ``3f2a91c0:12-14`` or ``3f2a91c0:5,9``."""
    document_id, _, paragraphs = spec.partition(":")
    document = application.library.get_document(document_id)
    numbers: list[int] = []
    for part in filter(None, (p.strip() for p in paragraphs.split(","))):
        first, _, last = part.lstrip("¶").partition("-")
        if not first.isdigit() or (last and not last.isdigit()):
            raise ValueError(f"'{spec}': paragraphs are written like 12, 12-14 or 5,9.")
        low, high = int(first), int(last or first)
        if high < low:
            raise ValueError(f"'{spec}': the range {part} runs backwards.")
        numbers.extend(range(low, high + 1))
    return SourceSelection.of(document, tuple(numbers))


def _print_comparison(comparison: SourceComparison) -> None:
    typer.secho(f"Comparing on: {comparison.subject}", bold=True)
    letters = {p.document_id: LETTERS[i] for i, p in enumerate(comparison.profiles)}
    for profile in comparison.profiles:
        typer.secho(f"\nSource {letters[profile.document_id]}: {profile.describe()}", bold=True)
        if profile.source_url:
            typer.echo(f"  {profile.source_url}")
        for source in comparison.passages_of(profile):
            typer.secho(f"  {source.label} {source.citation.locator}", fg=typer.colors.CYAN)
            text = source.citation.quoted_text
            if len(text) > SHOWN_PASSAGE_CHARS:
                text = text[:SHOWN_PASSAGE_CHARS].rstrip() + " […]"
            typer.echo(textwrap.indent(textwrap.fill(text, width=84), "    "))
            paragraph = source.citation.locator.lstrip("¶")
            typer.echo(f"    → praxis library read {str(profile.document_id)[:8]} --start {paragraph}")

    if comparison.comparability is not Comparability.UNKNOWN:
        note = f" — {comparison.comparability_note}" if comparison.comparability_note else ""
        typer.secho(f"\nComparability (AI-assessed): {comparison.comparability.value}{note}", bold=True)

    def marks(evidence: tuple[int, ...]) -> str:
        """``[1, 3] (sources A, B)``: the passages, and whose they are."""
        owners = dict.fromkeys(letters.get(_document_of(comparison, n), "?") for n in evidence)
        plural = "s" if len(owners) > 1 else ""
        return f" [{', '.join(map(str, evidence))}] (source{plural} {', '.join(owners)})"

    sections = [
        ("Shared ground (AI-generated)", comparison.similarities),
        ("Differences in treatment (AI-generated)", comparison.differences),
        ("Factual disagreements (AI-generated; check the passages)", comparison.disagreements),
        ("Observations on framing (AI interpretation, not established fact)", comparison.observations),
    ]
    for title, points in sections:
        if not points:
            continue
        typer.secho(f"\n{title}", bold=True)
        for point in points:
            aspect = f"{point.aspect}: " if point.aspect else ""
            typer.echo(textwrap.fill(
                aspect + point.description + marks(point.evidence),
                width=86, initial_indent="  - ", subsequent_indent="    ",
            ))
    if comparison.uncertainties:
        typer.secho("\nCould not be verified from these passages", fg=typer.colors.YELLOW)
        for note in comparison.uncertainties:
            typer.secho(textwrap.fill(note, width=86, initial_indent="  - ", subsequent_indent="    "), fg=typer.colors.YELLOW)
    typer.echo()
    _print_warnings(comparison.warnings, comparison.tokens_used)


def _document_of(comparison: SourceComparison, number: int):
    profile = comparison.source_of(number)
    return profile.document_id if profile else None


# --- news (F01) ----------------------------------------------------------------


@news_app.command("refresh")
def news_refresh() -> None:
    """Fetch the latest articles from every configured feed and keep them."""
    with session() as application:
        refresh = application.news.refresh()
    _print_refresh(refresh)


def _print_refresh(refresh: NewsRefresh) -> None:
    by_outlet: dict[str, int] = {}
    for article in refresh.fetched:
        by_outlet[article.outlet] = by_outlet.get(article.outlet, 0) + 1
    for outlet, count in by_outlet.items():
        typer.echo(f"{outlet}: {count} articles")
    for outlet, reason in refresh.failures:
        typer.secho(f"{outlet}: unavailable — {reason}", fg=typer.colors.YELLOW)
    typer.echo(f"{len(refresh.fetched)} articles fetched, {refresh.new_count} new.")
    if refresh.all_failed:
        typer.secho("No news source could be reached; earlier news is still shown by `news list`.", fg=typer.colors.YELLOW)
    elif refresh.is_limited:
        typer.secho("Some sources were unavailable, so the news is limited.", fg=typer.colors.YELLOW)


@news_app.command("list")
def news_list(
    days: Annotated[int, typer.Option(min=1, max=60, help="How many days back, today included.")] = 3,
    outlet: Annotated[Optional[str], typer.Option(help="Only this outlet (any part of its name).")] = None,
) -> None:
    """Stored headlines, newest first."""
    with session() as application:
        articles = application.news.get_recent_news(days)
    if outlet:
        articles = [a for a in articles if outlet.lower() in a.outlet.lower()]
    if not articles:
        typer.echo("No news stored for that period. Fetch it with: praxis news refresh")
        return
    for article in articles:
        when = article.publication_date.isoformat() if article.publication_date else "undated"
        typer.echo(f"{_short_id(article)}  {when}  {article.title}")
        typer.echo(f"          {article.outlet}  {article.source_url}")


@news_app.command("feeds")
def news_feeds() -> None:
    """The outlets news is fetched from (data/news/feeds.json)."""
    with session() as application:
        outlets = application.news.outlets
    for outlet in outlets:
        typer.echo(outlet)


# --- library (F05) -----------------------------------------------------------


@library_app.command("seed")
def library_seed(
    online: Annotated[bool, typer.Option(help="Download from Project Gutenberg instead of the bundled copies.")] = False,
) -> None:
    """Fill the library with the texts listed in the bundled catalogue."""
    with session() as application:
        library = application.library if online else bundled_library_service(application)
        report = library.import_catalogue()
    for document in report.imported:
        typer.echo(f"Imported {document.title}")
    for source_id, reason in report.failures:
        typer.secho(f"Skipped {source_id}: {reason}", fg=typer.colors.YELLOW)
    typer.echo(f"{len(report.imported)} imported, {len(report.failures)} skipped.")


@library_app.command("import")
def library_import(
    gutenberg_id: Annotated[str, typer.Argument(help="Project Gutenberg book number, e.g. 61.")],
    topic: Annotated[Optional[list[str]], typer.Option("--topic", "-t", help="Topic tag; repeatable.")] = None,
) -> None:
    """Download one public-domain book from Project Gutenberg."""
    with session() as application:
        document = application.library.import_document(
            SourceReference(gutenberg_id, topics=tuple(topic or ()))
        )
    typer.echo(f"Imported {document.title} [{_short_id(document)}]")


@library_app.command("search")
def library_search(
    query: Annotated[str, typer.Argument(help="Words to find in title, author, topics or text.")],
) -> None:
    """Search the library."""
    with session() as application:
        results = application.library.search(query)
    _print_documents(results, f"No texts match '{query}'. Try fewer or broader words.")


@library_app.command("browse")
def library_browse(
    topic: Annotated[Optional[str], typer.Option("--topic", "-t", help="Only texts with this topic.")] = None,
) -> None:
    """List texts, optionally filtered by topic."""
    with session() as application:
        empty = application.library.is_empty()
        documents = application.library.browse(topic)
    if empty:
        typer.echo("The library is empty. Run `praxis library seed` to add the sample texts.")
        return
    _print_documents(documents, f"No texts have the topic '{topic}'.")


@library_app.command("topics")
def library_topics() -> None:
    """List topics and how many texts each has."""
    with session() as application:
        topics = application.library.topics()
    for name, count in topics:
        typer.echo(f"{count:3}  {name}")


@library_app.command("read")
def library_read(
    document_id: Annotated[str, typer.Argument(help="Id or id prefix shown by search/browse.")],
    start: Annotated[int, typer.Option(help="First paragraph to show (1-based).", min=1)] = 1,
    count: Annotated[int, typer.Option(help="How many paragraphs to show.", min=1)] = 10,
    find: Annotated[Optional[str], typer.Option(help="Show only paragraphs containing these words.")] = None,
    annotations: Annotated[bool, typer.Option("--annotations", "-a", help="Show the AI annotations under their paragraphs.")] = False,
) -> None:
    """Read a text paragraph by paragraph. Progress is recorded in your profile."""
    with session() as application:
        document = application.library.get_document(document_id)
        passages = document.find_passages(find) if find else document.passages()
        shown = passages[start - 1 : start - 1 + count]
        if shown and not find:
            # Reading in order counts as progress; keyword lookups do not.
            application.events.publish(DocumentRead(document, start - 1 + len(shown)))
        by_passage: dict = {}
        for annotation in application.annotations.annotations_for(document):
            by_passage.setdefault(annotation.passage_id, []).append(annotation)

    typer.secho(f"{document.title} — {document.author}", bold=True)
    typer.echo(f"Source: {document.source_url or 'unknown'} | Licence: {document.license or 'unknown'}\n")
    if not shown:
        typer.echo("No paragraphs to show.")
        return
    for passage in shown:
        text = passage.text if document.can_reproduce() else document.cite(passage).quoted_text
        typer.echo(f"[{passage.locator}]")
        typer.echo(textwrap.fill(text, width=88) + "\n")
        notes = by_passage.get(passage.id, [])
        if notes and annotations:
            for annotation in notes:
                _print_annotation(annotation)
        elif notes:
            kinds = ", ".join(dict.fromkeys(a.type.label for a in notes))
            plural = "s" if len(notes) > 1 else ""
            typer.secho(f"  ✎ {len(notes)} AI annotation{plural} ({kinds}) — show with --annotations\n", fg=typer.colors.MAGENTA)
    remaining = len(passages) - (start - 1 + len(shown))
    if remaining > 0:
        typer.echo(f"… {remaining} more paragraphs. Next: --start {start + len(shown)}")


# --- annotations (F06) ----------------------------------------------------------

ANNOTATION_TYPES = ", ".join(t.value.replace("_", "-") for t in AnnotationType)


@app.command("annotate")
def annotate(
    document_id: Annotated[str, typer.Argument(help="Id or id prefix of the text.")],
    paragraph: Annotated[int, typer.Argument(help="Paragraph number, as in [¶12] from `library read`.", min=1)],
    kind: Annotated[str, typer.Option("--type", "-t", help=f"Kind of annotation: {ANNOTATION_TYPES}.")] = "argument",
) -> None:
    """Ask for an AI annotation of one paragraph; it is kept with the text."""
    with session() as application:  # inside, so a bad --type is reported, not raised
        annotation_type = AnnotationType.parse(kind)
        document = application.library.get_document(document_id)
        passage = document.paragraph(paragraph)
        result = application.annotations.generate_annotation(
            document, passage, annotation_type, application.profiles.get_profile()
        )

    typer.secho(f"{document.title} — {document.author}, {passage.locator}", bold=True)
    text = passage.text if document.can_reproduce() else document.cite(passage).quoted_text
    typer.echo(textwrap.fill(text, width=88) + "\n")
    _print_annotation_result(result)


def _print_annotation_result(result: AnnotationResult) -> None:
    if result.annotation is not None:
        _print_annotation(result.annotation)
    else:
        typer.secho("No annotation was written:", fg=typer.colors.YELLOW)
        for limitation in result.limitations:
            typer.secho(f"  - {limitation}", fg=typer.colors.YELLOW)
    _print_warnings(result.warnings, result.tokens_used)


def _print_annotation(annotation: Annotation) -> None:
    """An annotation, indented behind a bar so it never reads as the text."""
    label = f"AI annotation: {annotation.type.label}"
    if annotation.personalized:
        label += ", adapted to your reader profile"
    typer.secho(f"  ┃ {label}  [{str(annotation.id)[:8]}]", fg=typer.colors.MAGENTA, bold=True)
    for block in annotation.content.split("\n\n"):
        # Each line is wrapped on its own, so a "- " list keeps its items.
        for source_line in block.splitlines():
            bullet = source_line.lstrip()[:2] in {"- ", "* ", "• "}
            wrapped = textwrap.wrap(
                source_line.strip(), width=82, subsequent_indent="  " if bullet else ""
            )
            for line in wrapped:
                typer.secho(f"  ┃ {line}", fg=typer.colors.MAGENTA)
        typer.secho("  ┃", fg=typer.colors.MAGENTA)
    if annotation.uncertainties:
        typer.secho("  ┃ Could not be verified:", fg=typer.colors.YELLOW)
        for note in annotation.uncertainties:
            for number, line in enumerate(textwrap.wrap(note, width=78)):
                typer.secho(f"  ┃ {'- ' if number == 0 else '  '}{line}", fg=typer.colors.YELLOW)
    for number, citation in enumerate(annotation.sources, start=1):
        paragraph = citation.locator.lstrip("¶")
        typer.secho(f"  ┃ [{number}] {citation.format()}", fg=typer.colors.CYAN)
        typer.secho(
            f"  ┃     → praxis library read {str(citation.document_id)[:8]} --start {paragraph}",
            fg=typer.colors.CYAN,
        )
    typer.echo()


@annotations_app.command("list")
def annotations_list(
    document_id: Annotated[str, typer.Argument(help="Id or id prefix of the text.")],
) -> None:
    """Every AI annotation on a text, in text order."""
    with session() as application:
        document = application.library.get_document(document_id)
        notes = application.annotations.annotations_for(document)
    typer.secho(f"{document.title} — {document.author}", bold=True)
    if not notes:
        typer.echo("No annotations yet. Add one with: praxis annotate <id> <paragraph>")
        return
    for annotation in notes:
        typer.echo(f"\n[{annotation.locator}]")
        _print_annotation(annotation)


@annotations_app.command("remove")
def annotations_remove(
    annotation_id: Annotated[str, typer.Argument(help="Annotation id or prefix, shown in brackets.")],
) -> None:
    """Delete an annotation you do not want to keep."""
    with session() as application:
        found = application.annotations.find_annotation(annotation_id)
        application.annotations.remove_annotation(found)
    typer.echo(f"Removed annotation {str(found)[:8]}.")


@library_app.command("download")
def library_download(
    document_id: Annotated[str, typer.Argument(help="Id or id prefix shown by search/browse.")],
    to: Annotated[Path, typer.Option(help="Folder to save into.")] = Path("downloads"),
) -> None:
    """Save a public-domain text as a .txt file."""
    with session() as application:
        path = application.library.download(document_id, to)
    typer.echo(f"Saved to {path}")


# --- reader profile (F13) ----------------------------------------------------

_LEVELS = {level.name.lower(): level for level in KnowledgeLevel}


def _parse_level(name: str) -> KnowledgeLevel:
    try:
        return _LEVELS[name.strip().lower()]
    except KeyError:
        raise ValueError(f"Level must be one of: {', '.join(_LEVELS)}.") from None


def _print_profile(profile: ReaderProfile) -> None:
    if profile.is_sparse:
        typer.echo("Nothing is known about you yet. Read, research, or add interests to build your profile.\n")
    typer.secho("Knowledge", bold=True)
    for area in sorted(profile.knowledge.areas.values(), key=lambda a: a.topic):
        origin = "you said" if not area.is_inferred else f"inferred from {area.evidence} activit{'y' if area.evidence == 1 else 'ies'}"
        typer.echo(f"  {area.topic}: {area.level.name.lower()} ({origin})")
    typer.secho("Interests", bold=True)
    for topic in profile.interests.top(10):
        typer.echo(f"  {topic}")
    typer.secho("Reading", bold=True)
    for record in profile.history.recent():
        status = "finished" if record.completed else f"{record.progress:.0%}"
        typer.echo(f"  {record.title}: {status}")
    typer.secho("Preferences", bold=True)
    typer.echo(f"  explanation depth: {profile.explanation_depth.value}")
    typer.echo(f"  personalization: {'on' if profile.personalization_enabled else 'off'}")
    if profile.background:
        typer.echo(f"  background: {profile.background}")


@profile_app.command("show")
def profile_show() -> None:
    """Show everything the system believes about you, and where it came from."""
    with session() as application:
        profile = application.profiles.get_profile()
    _print_profile(profile)


@profile_app.command("know")
def profile_know(
    topic: Annotated[str, typer.Argument(help="Topic, e.g. 'surplus value'.")],
    level: Annotated[str, typer.Argument(help="none, introductory, intermediate or advanced.")],
) -> None:
    """State your level on a topic. Overrides anything inferred."""
    with session() as application:
        parsed = _parse_level(level)
        application.profiles.correct_knowledge_assessment(topic, parsed)
    typer.echo(f"Recorded: {topic.strip().lower()} = {parsed.name.lower()} (stated by you).")


@profile_app.command("forget")
def profile_forget(topic: Annotated[str, typer.Argument(help="Topic to remove from your knowledge.")]) -> None:
    """Remove a knowledge assessment."""
    with session() as application:
        removed = application.profiles.remove_knowledge_assessment(topic)
    typer.echo("Removed." if removed else f"No assessment for '{topic}'.")


@profile_app.command("interest")
def profile_interest(
    topic: Annotated[str, typer.Argument(help="Topic of interest.")],
    remove: Annotated[bool, typer.Option("--remove", help="Remove instead of add; it will not be re-inferred.")] = False,
) -> None:
    """Add or remove an interest."""
    with session() as application:
        if remove:
            removed = application.profiles.remove_interest(topic)
            message = "Removed." if removed else "Not an interest; it will not be inferred in future."
        else:
            application.profiles.add_interest(topic)
            message = "Added."
    typer.echo(message)


@profile_app.command("depth")
def profile_depth(depth: Annotated[ExplanationDepth, typer.Argument(help="How detailed explanations should be.")]) -> None:
    """Set how detailed explanations should be."""
    with session() as application:
        application.profiles.set_explanation_depth(depth)
    typer.echo(f"Explanation depth set to {depth.value}.")


@profile_app.command("personalize")
def profile_personalize(enabled: Annotated[bool, typer.Argument(help="true or false.")]) -> None:
    """Turn personalization on or off."""
    with session() as application:
        application.profiles.set_personalization(enabled)
    typer.echo(f"Personalization {'on' if enabled else 'off'}.")


@profile_app.command("background")
def profile_background(text: Annotated[str, typer.Argument(help="Anything you want the agent to know about you.")]) -> None:
    """Tell the agent about your background in your own words."""
    with session() as application:
        application.profiles.set_background(text)
    typer.echo("Background saved.")


@profile_app.command("reset")
def profile_reset(
    yes: Annotated[bool, typer.Option("--yes", help="Confirm without asking.")] = False,
) -> None:
    """Forget everything known about you."""
    if not yes and not typer.confirm("Erase your whole reader profile?"):
        raise typer.Exit()
    with session() as application:
        application.profiles.reset()
    typer.echo("Profile erased.")


# --- workspace (F15) ---------------------------------------------------------


def _print_items(items: list[SavedItem], empty_message: str) -> None:
    if not items:
        typer.echo(empty_message)
        return
    for item in items:
        typer.echo(f"{str(item.id)[:8]}  [{item.kind.value}] {item.title}")
        details = [f"saved {item.saved_at:%Y-%m-%d %H:%M}"]
        if item.tags:
            details.append("tags: " + ", ".join(item.tags))
        typer.echo("          " + " | ".join(details))
        if item.note:
            typer.echo(f"          note: {item.note}")


@workspace_app.command("list")
def workspace_list(
    kind: Annotated[Optional[SavedItemKind], typer.Option(help="Only items of this kind.")] = None,
) -> None:
    """List saved items, newest first."""
    with session() as application:
        items = application.workspace.get_workspace().newest_first(kind)
    _print_items(items, "Your workspace is empty. Save texts with `praxis workspace save-text`.")


@workspace_app.command("save-text")
def workspace_save_text(
    document_id: Annotated[str, typer.Argument(help="Library id or prefix.")],
    note: Annotated[str, typer.Option(help="Your note about it.")] = "",
    tag: Annotated[Optional[list[str]], typer.Option("--tag", "-t", help="Tag; repeatable.")] = None,
) -> None:
    """Save a library text to your workspace."""
    with session() as application:
        document = application.library.get_document(document_id)
        item = application.workspace.save_document(document, note, tuple(tag or ()))
    typer.echo(f"Saved {item.title} [{str(item.id)[:8]}]")


@workspace_app.command("save-passage")
def workspace_save_passage(
    document_id: Annotated[str, typer.Argument(help="Library id or prefix.")],
    paragraph: Annotated[int, typer.Argument(help="Paragraph number, as shown by `library read` (¶n).", min=1)],
    note: Annotated[str, typer.Option(help="Your note about it.")] = "",
    tag: Annotated[Optional[list[str]], typer.Option("--tag", "-t", help="Tag; repeatable.")] = None,
) -> None:
    """Save one paragraph of a text, with its citation."""
    with session() as application:
        document = application.library.get_document(document_id)
        passages = document.passages()
        if paragraph > len(passages):
            raise ValueError(f"“{document.title}” has only {len(passages)} paragraphs.")
        item = application.workspace.save_passage(
            document, passages[paragraph - 1], note, tuple(tag or ())
        )
    typer.echo(f"Saved {item.title} [{str(item.id)[:8]}]")


@workspace_app.command("note")
def workspace_note(
    title: Annotated[str, typer.Argument(help="Short title.")],
    text: Annotated[str, typer.Argument(help="The note itself.")] = "",
    tag: Annotated[Optional[list[str]], typer.Option("--tag", "-t", help="Tag; repeatable.")] = None,
) -> None:
    """Write a free-standing note."""
    with session() as application:
        item = application.workspace.add_note(title, text, tuple(tag or ()))
    typer.echo(f"Saved note [{str(item.id)[:8]}]")


@workspace_app.command("search")
def workspace_search(query: Annotated[str, typer.Argument(help="Words to find.")]) -> None:
    """Search titles, content, notes and tags of saved items."""
    with session() as application:
        items = application.workspace.search(query)
    _print_items(items, f"Nothing saved matches '{query}'.")


@workspace_app.command("open")
def workspace_open(item_id: Annotated[str, typer.Argument(help="Item id or prefix.")]) -> None:
    """Show a saved item and how to continue from it."""
    with session() as application:
        item = application.workspace.get_item(item_id)
        research_id = application.workspace.research_session_of(item)
        comparison_id = application.workspace.comparison_of(item)
        document_id = application.workspace.document_id_of(item)
        paragraph = application.workspace.paragraph_of(item)
        still_available = False
        if document_id is not None:
            try:
                application.library.get_document(document_id)
                still_available = True
            except LibraryError:
                pass
        progress = (
            application.profiles.get_profile().history.get(document_id) if document_id else None
        )

    typer.secho(f"[{item.kind.value}] {item.title}", bold=True)
    if item.content:
        typer.echo(textwrap.fill(item.content, width=88))
    if item.note:
        typer.echo(f"\nNote: {item.note}")
    if comparison_id is not None:
        typer.echo(f"\n→ praxis comparisons show {str(comparison_id)[:8]}")
    if research_id is not None:
        short = str(research_id)[:8]
        typer.echo(f"\n→ praxis sessions show {short}")
        typer.echo(f'→ praxis sessions continue {short} --focus "..."')
    if document_id is None:
        return
    if not still_available:
        typer.secho(
            "\nThe original text is no longer in the library; the saved copy above is what remains.",
            fg=typer.colors.YELLOW,
        )
        return
    resume_at = paragraph or (progress.furthest_paragraph + 1 if progress and not progress.completed else 1)
    typer.echo(f"\nContinue reading: praxis library read {str(document_id)[:8]} --start {resume_at}")


@workspace_app.command("remove")
def workspace_remove(item_id: Annotated[str, typer.Argument(help="Item id or prefix.")]) -> None:
    """Remove a saved item."""
    with session() as application:
        item = application.workspace.remove_item(item_id)
    typer.echo(f"Removed {item.title}.")


def main() -> None:
    app()
