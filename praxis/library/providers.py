"""Where library texts come from.

``DocumentProvider`` is the application's own interface for an external text
archive. ``PublicTextArchiveAdapter`` adapts Project Gutenberg's plain-text
files to it, so the rest of the system only ever sees ``Document`` objects.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from praxis.documents import Book, Document

GUTENBERG_MIRROR = "https://gutenberg.pglaf.org"
GUTENBERG_LICENSE = "Public domain (Project Gutenberg)"

# Markers end with "***", sometimes after a title wrapped onto a second line.
_START = re.compile(r"^\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG[^*]*\*\*\*", re.M)
_END = re.compile(r"^\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG[^*]*\*\*\*", re.M)
_OLD_END = re.compile(r"^End of (the )?Project Gutenberg", re.M | re.I)
_HEADER_FIELD =re.compile(r"^(Title|Author):\s*(.+)$", re.M)


class ProviderError(Exception):
    """The external archive could not supply the requested text."""


@dataclass(frozen=True)
class SourceReference:
    """What the caller knows about a text before it is fetched."""

    source_id: str
    topics: tuple[str, ...] = ()
    title: str = ""
    author: str = ""


class DocumentProvider(ABC):
    @abstractmethod
    def fetch(self, reference: SourceReference) -> Document:
        """Fetch one text and return it as a ``Document``, or raise
        ``ProviderError``."""


Fetcher = Callable[[str], str]


def _http_get(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ProviderError(f"Could not download {url}: {exc}") from exc


class PublicTextArchiveAdapter(DocumentProvider):
    """Adapter for Project Gutenberg plain-text e-books.

    ``fetcher`` turns a URL into text. It defaults to a real HTTP request;
    tests pass a fake so they never touch the network.
    """

    def __init__(
        self, base_url: str = GUTENBERG_MIRROR, fetcher: Fetcher = _http_get
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._fetch = fetcher

    def url_for(self, source_id: str) -> str:
        """Mirror layout: book 1346 lives at /1/3/4/1346/1346-0.txt."""
        if not source_id.isdigit():
            raise ProviderError(f"'{source_id}' is not a Gutenberg book number.")
        folders = "/".join(source_id[:-1]) if len(source_id) > 1 else "0"
        return f"{self._base_url}/{folders}/{source_id}/{source_id}-0.txt"

    def fetch(self, reference: SourceReference) -> Document:
        raw = self._fetch(self.url_for(reference.source_id))
        header = _header_fields(raw)
        title = reference.title or header.get("Title", "")
        author = reference.author or header.get("Author", "Unknown")
        if not title:
            raise ProviderError(f"Book {reference.source_id} has no title.")
        return Book(
            title=title,
            author=author,
            text=clean_text(raw),
            source_url=f"https://www.gutenberg.org/ebooks/{reference.source_id}",
            license=GUTENBERG_LICENSE,
            downloadable=True,
            topics=reference.topics,
        )


def _header_fields(raw: str) -> dict[str, str]:
    start = _START.search(raw)
    header = raw[: start.start()] if start else ""
    return {key: value.strip() for key, value in _HEADER_FIELD.findall(header)}


def clean_text(raw: str) -> str:
    """Keep only the book itself, with each paragraph on one line.

    Gutenberg files wrap prose at about 70 columns and wrap the book in a
    licence header and footer. Passages are split on blank lines, so the hard
    line breaks inside each paragraph are joined back together.
    """
    text = raw.replace("\r\n", "\n").lstrip("﻿")
    start = _START.search(text)
    if start:
        text = text[start.end() :]
    end = _END.search(text)
    if end:
        text = text[: end.start()]
    # Older files also close with a plain "End of Project Gutenberg's ..." line.
    text = _OLD_END.split(text)[0]
    paragraphs = re.split(r"\n\s*\n", text)
    joined = (" ".join(line.strip() for line in p.splitlines()) for p in paragraphs)
    return "\n\n".join(p for p in (re.sub(r"\s+", " ", j).strip() for j in joined) if p)
