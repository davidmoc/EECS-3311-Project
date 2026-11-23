"""What source discovery works with: requests, found links and reports."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from praxis.documents import Document


@dataclass(frozen=True)
class DiscoveryRequest:
    """A topic to find texts on, and the narrower subtopics it involves
    (a learning path's prerequisites, a research plan's searches)."""

    topic: str
    subtopics: tuple[str, ...] = ()


@dataclass(frozen=True)
class FoundSource:
    """A text a finder pointed to, before it is read.

    ``text`` is set when the finder already has the text (Wikipedia's API
    returns it); otherwise the page at ``url`` is read. ``subtopic`` is
    the part of the request the text was found for.
    """

    url: str
    title: str = ""
    author: str = ""
    year: int | None = None
    subtopic: str = ""
    text: str = ""
    license: str = ""

    @property
    def key(self) -> str:
        return normalize_url(self.url)


@dataclass(frozen=True)
class FinderResult:
    sources: tuple[FoundSource, ...] = ()
    tokens_used: int = 0


@dataclass(frozen=True)
class DiscoveryReport:
    """What one discovery added to the library.

    ``added`` are texts saved now; ``held`` were found again but were
    already in the library. ``failures`` are (url or finder, reason).
    """

    topic: str
    added: tuple[Document, ...] = ()
    held: tuple[Document, ...] = ()
    failures: tuple[tuple[str, str], ...] = ()
    tokens_used: int = 0

    @property
    def documents(self) -> tuple[Document, ...]:
        """Every text found for the request, new or already held."""
        return self.added + self.held

    def note(self) -> str | None:
        """One line for the reader saying what was added, if anything."""
        if not self.added:
            if self.failures and not self.held:
                return (
                    "No new texts could be found on the web for this topic "
                    f"({len(self.failures)} attempt{'s' if len(self.failures) != 1 else ''} failed), "
                    "so only the library was searched."
                )
            return None
        titles = "; ".join(f"“{d.title}”" for d in self.added[:6])
        more = f" and {len(self.added) - 6} more" if len(self.added) > 6 else ""
        return (
            f"Found {len(self.added)} new text{'s' if len(self.added) != 1 else ''} "
            f"on the web and added {'them' if len(self.added) != 1 else 'it'} "
            f"to your library: {titles}{more}."
        )


def normalize_url(url: str) -> str:
    """The same page under one spelling: no fragment, no trailing slash,
    lower-case scheme and host, ``http`` read as ``https``."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme == "http":
        scheme = "https"
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, parts.netloc.lower(), path, parts.query, ""))
