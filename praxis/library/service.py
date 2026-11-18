"""The reading library (F05): search, browse, open and download texts."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import UUID

from praxis.documents import Document
from praxis.library.providers import DocumentProvider, ProviderError, SourceReference
from praxis.persistence import DocumentRepository

DEFAULT_CATALOGUE = Path("data/library/catalogue.json")


class LibraryError(Exception):
    """A library request could not be completed; the message says why."""


@dataclass(frozen=True)
class ImportReport:
    imported: tuple[Document, ...]
    failures: tuple[tuple[str, str], ...]  # (source id, reason)


class LibraryService:
    def __init__(
        self, documents: DocumentRepository, provider: DocumentProvider | None = None
    ) -> None:
        self._documents = documents
        self._provider = provider

    # --- finding texts -----------------------------------------------------

    def search(self, query: str) -> list[Document]:
        return self._documents.search(query)

    def browse(self, topic: str | None = None) -> list[Document]:
        """All texts, or only those tagged with ``topic`` (any letter case)."""
        documents = self._documents.list_all()
        if topic is None:
            return documents
        wanted = topic.strip().lower()
        return [d for d in documents if wanted in (t.lower() for t in d.topics)]

    def topics(self) -> list[tuple[str, int]]:
        """Each topic with how many texts carry it, most common first."""
        counts = Counter(
            t.lower() for d in self._documents.list_all() for t in d.topics
        )
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    def get_document(self, document_id: UUID | str) -> Document:
        """Look a text up by full id, or by an unambiguous id prefix such as
        the eight characters the CLI prints."""
        if isinstance(document_id, UUID):
            document = self._documents.find_by_id(document_id)
            if document is None:
                raise LibraryError(f"No text with id {document_id}.")
            return document

        prefix = document_id.strip().lower()
        if not prefix:
            raise LibraryError("A document id is required.")
        matches = [d for d in self._documents.list_all() if str(d.id).startswith(prefix)]
        if not matches:
            raise LibraryError(f"No text with id starting '{prefix}'.")
        if len(matches) > 1:
            raise LibraryError(f"Id '{prefix}' matches {len(matches)} texts; use more characters.")
        return matches[0]

    # --- getting texts out -------------------------------------------------

    def download(self, document_id: UUID | str, destination: Path | str) -> Path:
        """Write the full text to a ``.txt`` file in ``destination``.

        Only texts whose licence allows reproduction may be downloaded.
        """
        document = self.get_document(document_id)
        if not (document.downloadable and document.can_reproduce()):
            raise LibraryError(
                f"“{document.title}” may not be downloaded"
                + (f"; see {document.source_url}" if document.source_url else ".")
            )
        folder = Path(destination)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{_slug(document.title)}.txt"
        path.write_text(
            f"{document.title}\n{document.author}\n"
            f"Source: {document.source_url}\nLicence: {document.license}\n\n"
            + document.text,
            encoding="utf-8",
        )
        return path

    # --- adding texts ------------------------------------------------------

    def import_document(self, reference: SourceReference) -> Document:
        if self._provider is None:
            raise LibraryError("No document archive is configured.")
        try:
            document = self._provider.fetch(reference)
        except ProviderError as exc:
            raise LibraryError(str(exc)) from exc
        self._documents.save(document)
        return document

    def import_catalogue(self, catalogue: Path | str = DEFAULT_CATALOGUE) -> ImportReport:
        """Import every text listed in a catalogue file.

        One unavailable text does not stop the rest; failures are reported.
        """
        imported, failures = [], []
        for reference in read_catalogue(catalogue):
            try:
                imported.append(self.import_document(reference))
            except LibraryError as exc:
                failures.append((reference.source_id, str(exc)))
        return ImportReport(tuple(imported), tuple(failures))

    def is_empty(self) -> bool:
        return not self._documents.list_all()


def read_catalogue(path: Path | str) -> list[SourceReference]:
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LibraryError(f"Cannot read catalogue {path}: {exc}") from exc
    return [
        SourceReference(
            source_id=str(entry["source_id"]),
            title=entry.get("title", ""),
            author=entry.get("author", ""),
            topics=tuple(entry.get("topics", ())),
            publication_date=date.fromisoformat(entry["publication_date"])
            if entry.get("publication_date")
            else None,
        )
        for entry in entries
    ]


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "document"
