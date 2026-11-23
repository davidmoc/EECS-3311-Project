"""Growing the library on demand (source discovery).

When the reader researches a question or builds a learning path, the
library may hold nothing on it: a current event, a country, a movement.
``SourceDiscoveryService.discover`` asks each ``SourceFinder`` for texts on
the topic, reads the pages it has not stored yet, and saves them to the
library as articles, tagged with the topic. The features then search the
library as before and find them there, so every reading stays a real,
citable passage with a link back to where it came from.

Pages are downloaded in parallel; they are saved on the calling thread,
because the database connection belongs to it.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

from praxis.discovery.finders import DiscoveryError, SourceFinder
from praxis.discovery.models import (
    DiscoveryReport,
    DiscoveryRequest,
    FinderResult,
    FoundSource,
    normalize_url,
)
from praxis.discovery.pages import WebPage, WebPageReader
from praxis.documents import Article, Document
from praxis.persistence import DocumentRepository

MAX_NEW_TEXTS = 10
DOWNLOAD_WORKERS = 6
MAX_SUBTOPICS = 8
WEB_LICENSE = "© {owner}; saved for personal research, quoted in excerpts only"


class SourceDiscoveryService:
    def __init__(
        self,
        documents: DocumentRepository,
        finders: list[SourceFinder],
        reader: WebPageReader | None = None,
        max_new: int = MAX_NEW_TEXTS,
    ) -> None:
        self._documents = documents
        self._finders = list(finders)
        self._reader = reader or WebPageReader()
        self._max_new = max_new

    @property
    def finder_names(self) -> list[str]:
        return [finder.name for finder in self._finders]

    def discover(self, topic: str, subtopics: list[str] | tuple[str, ...] = ()) -> DiscoveryReport:
        """Find texts on ``topic`` (and each of ``subtopics``) and add the
        new ones to the library. Never raises for a failed search or page;
        those are reported in ``failures``."""
        topic = " ".join(topic.split())
        if not topic:
            return DiscoveryReport(topic)
        cleaned = [" ".join(s.split()) for s in subtopics]
        request = DiscoveryRequest(
            topic, tuple(dict.fromkeys(s for s in cleaned if s and s.lower() != topic.lower()))[:MAX_SUBTOPICS]
        )

        failures: list[tuple[str, str]] = []
        tokens = 0
        found: dict[str, FoundSource] = {}
        # Finders search at the same time; their results are merged in
        # finder order, so for a page two finders found, the earlier
        # finder's copy is kept.
        for finder, outcome in zip(self._finders, self._run_finders(request)):
            if isinstance(outcome, DiscoveryError):
                failures.append((finder.name, str(outcome)))
                continue
            tokens += outcome.tokens_used
            for source in outcome.sources:
                found.setdefault(source.key, source)

        held: list[Document] = []
        to_read: list[FoundSource] = []
        for source in found.values():
            existing = self._documents.find_by_id(document_id(source.url))
            if existing is not None:
                held.append(existing)
            elif len(to_read) < self._max_new:
                to_read.append(source)

        added: list[Document] = []
        for source, outcome in zip(to_read, self._read_all(to_read)):
            if isinstance(outcome, DiscoveryError):
                failures.append((source.url, str(outcome)))
                continue
            document = to_document(source, outcome, request.topic)
            if document.text.strip():
                self._documents.save(document)
                added.append(document)
        return DiscoveryReport(topic, tuple(added), tuple(held), tuple(failures), tokens)

    def _run_finders(self, request: DiscoveryRequest) -> list[FinderResult | DiscoveryError]:
        def run(finder: SourceFinder) -> FinderResult | DiscoveryError:
            try:
                return finder.find(request)
            except DiscoveryError as exc:
                return exc
            except Exception as exc:  # one broken finder must not stop the others
                return DiscoveryError(f"the search failed ({exc})")

        if len(self._finders) <= 1:
            return [run(f) for f in self._finders]
        with ThreadPoolExecutor(max_workers=len(self._finders)) as pool:
            return list(pool.map(run, self._finders))

    def _read_all(self, sources: list[FoundSource]) -> list[WebPage | None | DiscoveryError]:
        """Each source's page (``None`` when the finder gave the text), or
        why it could not be read, in the order of ``sources``."""
        def read(source: FoundSource) -> WebPage | None | DiscoveryError:
            if source.text:
                return None
            try:
                return self._reader.read(source.url)
            except DiscoveryError as exc:
                return exc
            except Exception as exc:  # one bad page must not stop the rest
                return DiscoveryError(f"could not be read ({exc})")

        if len(sources) <= 1:
            return [read(s) for s in sources]
        with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
            return list(pool.map(read, sources))


def document_id(url: str) -> UUID:
    """Same page, same id: finding it again does not store it twice."""
    return uuid5(NAMESPACE_URL, normalize_url(url))


def to_document(source: FoundSource, page: WebPage | None, topic: str) -> Document:
    """The found text as a library article, tagged with the topic and the
    subtopic it was found for."""
    topics = tuple(dict.fromkeys(t for t in (topic, source.subtopic) if t))
    if page is None:  # the finder supplied the text
        return Article(
            id=document_id(source.url),
            title=source.title or source.url,
            author=source.author or "Unknown",
            text=source.text,
            publication_date=date(source.year, 1, 1) if source.year else None,
            source_url=source.url,
            license=source.license or WEB_LICENSE.format(owner=_host(source.url)),
            downloadable=bool(source.license),
            topics=topics,
        )
    owner = page.site or _host(source.url)
    return Article(
        id=document_id(source.url),
        # The page's own title and byline first; the finder's as fallback.
        title=page.title or source.title or source.url,
        author=page.author or source.author or owner,
        text=page.text,
        publication_date=_date(page.published) or (date(source.year, 1, 1) if source.year else None),
        source_url=source.url,
        license=WEB_LICENSE.format(owner=owner),
        downloadable=False,
        topics=topics,
    )


def _host(url: str) -> str:
    return urlsplit(url).netloc.removeprefix("www.") or "the publisher"


def _date(value: str) -> date | None:
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if not match:
        return None
    try:
        return date(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:
        return None
