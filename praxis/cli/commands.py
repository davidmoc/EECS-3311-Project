"""Command-line interface.

Each command is a thin controller: it parses arguments, calls a service from
the shared ``Application``, and prints the result. No business logic here.

Python note: Typer reads each function's parameters and type hints to build
the command's arguments and options, so the signatures below *are* the CLI.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Annotated, Optional

import typer

from praxis.app import Application, build_application, bundled_library_service
from praxis.documents import Document
from praxis.library import LibraryError, SourceReference

app = typer.Typer(help="Praxis: Marxist political research and learning.", no_args_is_help=True)
library_app = typer.Typer(help="Browse, search and read the text library (F05).", no_args_is_help=True)
app.add_typer(library_app, name="library")

# Tests replace this to run commands against an in-memory database.
application_factory = build_application


def _open() -> Application:
    return application_factory()


def _fail(message: str) -> None:
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


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


@library_app.command("seed")
def library_seed(
    online: Annotated[bool, typer.Option(help="Download from Project Gutenberg instead of the bundled copies.")] = False,
) -> None:
    """Fill the library with the texts listed in the bundled catalogue."""
    application = _open()
    try:
        library = application.library if online else bundled_library_service(application)
        report = library.import_catalogue()
    except LibraryError as exc:
        _fail(str(exc))
    finally:
        application.close()
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
    application = _open()
    try:
        document = application.library.import_document(
            SourceReference(gutenberg_id, topics=tuple(topic or ()))
        )
    except LibraryError as exc:
        _fail(str(exc))
    finally:
        application.close()
    typer.echo(f"Imported {document.title} [{_short_id(document)}]")


@library_app.command("search")
def library_search(
    query: Annotated[str, typer.Argument(help="Words to find in title, author, topics or text.")],
) -> None:
    """Search the library."""
    application = _open()
    try:
        results = application.library.search(query)
    finally:
        application.close()
    _print_documents(results, f"No texts match '{query}'. Try fewer or broader words.")


@library_app.command("browse")
def library_browse(
    topic: Annotated[Optional[str], typer.Option("--topic", "-t", help="Only texts with this topic.")] = None,
) -> None:
    """List texts, optionally filtered by topic."""
    application = _open()
    try:
        library = application.library
        documents = library.browse(topic)
        empty = library.is_empty()
    finally:
        application.close()
    if empty:
        typer.echo("The library is empty. Run `praxis library seed` to add the sample texts.")
        return
    _print_documents(documents, f"No texts have the topic '{topic}'.")


@library_app.command("topics")
def library_topics() -> None:
    """List topics and how many texts each has."""
    application = _open()
    try:
        topics = application.library.topics()
    finally:
        application.close()
    for name, count in topics:
        typer.echo(f"{count:3}  {name}")


@library_app.command("read")
def library_read(
    document_id: Annotated[str, typer.Argument(help="Id or id prefix shown by search/browse.")],
    start: Annotated[int, typer.Option(help="First paragraph to show (1-based).", min=1)] = 1,
    count: Annotated[int, typer.Option(help="How many paragraphs to show.", min=1)] = 10,
    find: Annotated[Optional[str], typer.Option(help="Show only paragraphs containing these words.")] = None,
) -> None:
    """Read a text paragraph by paragraph."""
    application = _open()
    try:
        document = application.library.get_document(document_id)
    except LibraryError as exc:
        _fail(str(exc))
    finally:
        application.close()

    passages = document.find_passages(find) if find else document.passages()
    shown = passages[start - 1 : start - 1 + count]
    typer.secho(f"{document.title} — {document.author}", bold=True)
    typer.echo(f"Source: {document.source_url or 'unknown'} | Licence: {document.license or 'unknown'}\n")
    if not shown:
        typer.echo("No paragraphs to show.")
        return
    for passage in shown:
        text = passage.text if document.can_reproduce() else document.cite(passage).quoted_text
        typer.echo(f"[{passage.locator}]")
        typer.echo(textwrap.fill(text, width=88) + "\n")
    remaining = len(passages) - (start - 1 + len(shown))
    if remaining > 0:
        typer.echo(f"… {remaining} more paragraphs. Next: --start {start + len(shown)}")


@library_app.command("download")
def library_download(
    document_id: Annotated[str, typer.Argument(help="Id or id prefix shown by search/browse.")],
    to: Annotated[Path, typer.Option(help="Folder to save into.")] = Path("downloads"),
) -> None:
    """Save a public-domain text as a .txt file."""
    application = _open()
    try:
        path = application.library.download(document_id, to)
    except LibraryError as exc:
        _fail(str(exc))
    finally:
        application.close()
    typer.echo(f"Saved to {path}")


def main() -> None:
    app()
