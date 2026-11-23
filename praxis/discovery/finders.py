"""Where texts beyond the library are found (Strategy).

``SourceFinder`` is the application's interface for something that can
point to texts on a topic. Two are provided:

* ``WebSearchSourceFinder`` asks a model with web search for substantive,
  freely readable articles, analyses and essays, from a range of outlets
  including Marxist and left publications.
* ``WikipediaSourceFinder`` uses Wikipedia's public API for encyclopaedic
  background. Its texts are CC BY-SA, so they may be shown in full.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable

from praxis.discovery.models import DiscoveryRequest, FinderResult, FoundSource
from praxis.llm import LLMError, Prompt, WebSearchClient

USER_AGENT = "Praxis/0.1 (course project; research reader)"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_LICENSE = "CC BY-SA 4.0 (Wikipedia contributors)"
# Sections at the end of an article that are lists, not prose.
_WIKIPEDIA_TAIL = re.compile(
    r"^=+\s*(See also|References|Notes|Citations|Sources|Footnotes|External links|"
    r"Further reading|Bibliography|Works cited)\s*=+\s*$",
    re.IGNORECASE,
)
_WIKIPEDIA_HEADING = re.compile(r"^=+\s*(.*?)\s*=+\s*$")
_MIN_WIKIPEDIA_CHARS = 600

# "https://… | title | author or outlet | year | subtopic"
_SOURCE_LINE = re.compile(r"(https?://[^\s|<>\"]+)\s*\|(.*)$")


class DiscoveryError(Exception):
    """A finder could not search; the message says why."""


class SourceFinder(ABC):
    name: str

    @abstractmethod
    def find(self, request: DiscoveryRequest) -> FinderResult:
        """Texts on the request's topic, best first, or raise
        ``DiscoveryError``."""


JsonFetcher = Callable[[str], dict]


def _http_get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise DiscoveryError(f"Could not reach {urllib.parse.urlsplit(url).netloc}: {exc}") from exc


class WikipediaSourceFinder(SourceFinder):
    """Up to ``per_topic`` articles for the topic and ``per_subtopic`` for
    each subtopic, with their plain text. ``fetcher`` turns a URL into
    parsed JSON; tests pass a fake so they never touch the network."""

    name = "Wikipedia"

    def __init__(
        self, fetcher: JsonFetcher = _http_get_json, per_topic: int = 2, per_subtopic: int = 1
    ) -> None:
        self._fetch = fetcher
        self._per_topic = per_topic
        self._per_subtopic = per_subtopic

    def find(self, request: DiscoveryRequest) -> FinderResult:
        titles: dict[str, str] = {}  # article title -> subtopic it was found for
        searches = [(request.topic, self._per_topic, "")]
        searches += [(s, self._per_subtopic, s) for s in request.subtopics]
        for query, limit, subtopic in searches:
            if limit < 1:
                continue
            for title in self._search(query, limit):
                titles.setdefault(title, subtopic)
        if not titles:
            return FinderResult()
        pages = self._extracts(list(titles))
        sources = []
        for title, subtopic in titles.items():
            page = pages.get(title)
            if page is None:
                continue
            text = wikipedia_text(page.get("extract", ""))
            if len(text) < _MIN_WIKIPEDIA_CHARS:
                continue
            sources.append(FoundSource(
                url=page.get("fullurl") or _wikipedia_url(title),
                title=title,
                author="Wikipedia contributors",
                subtopic=subtopic,
                text=text,
                license=WIKIPEDIA_LICENSE,
            ))
        return FinderResult(tuple(sources))

    def _search(self, query: str, limit: int) -> list[str]:
        data = self._fetch(WIKIPEDIA_API + "?" + urllib.parse.urlencode({
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": limit, "format": "json", "formatversion": 2,
        }))
        return [hit["title"] for hit in data.get("query", {}).get("search", []) if hit.get("title")]

    def _extracts(self, titles: list[str]) -> dict[str, dict]:
        pages: dict[str, dict] = {}
        # The API returns whole-article extracts for one page per request.
        for title in titles:
            data = self._fetch(WIKIPEDIA_API + "?" + urllib.parse.urlencode({
                "action": "query", "prop": "extracts|info", "explaintext": 1,
                "inprop": "url", "redirects": 1, "titles": title,
                "format": "json", "formatversion": 2,
            }))
            for page in data.get("query", {}).get("pages", []):
                if not page.get("missing"):
                    pages[title] = page
        return pages


def _wikipedia_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


def wikipedia_text(extract: str) -> str:
    """A plain-text extract as paragraphs separated by blank lines, without
    headings and without the reference sections at the end."""
    paragraphs = []
    for line in extract.splitlines():
        line = line.strip()
        if _WIKIPEDIA_TAIL.match(line):
            break
        if not line or _WIKIPEDIA_HEADING.match(line):
            continue
        paragraphs.append(line)
    return "\n\n".join(paragraphs)


SEARCH_SYSTEM = (
    "You find readings for a political research and study tool used by "
    "readers learning Marxist analysis. You search the web and reply only "
    "in the line format asked for."
)
SEARCH_TEMPLATE = """Search the web for up to {count} substantive texts that a reader should read to understand: {topic}
{subtopics}
What to look for:
- Full articles, analyses, essays, reports, book chapters and primary documents that are genuinely about this topic (not loosely related theory, not one-paragraph news briefs, not listings or search pages).
- Texts whose full text is freely readable as an ordinary web page: no paywalls, no login, no PDF files, no videos.
- A range of perspectives: include Marxist and left analysis (for example marxists.org, Monthly Review, Peoples Dispatch, Jacobin, Black Agenda Report, MERIP, Counterpunch, Tricontinental) as well as solid reporting and scholarship.
- For a current event, prefer recent coverage and analysis; for history, prefer the best-known accounts and primary sources.

Reply with one line per text and nothing else:
URL | title | author or outlet | year | which part of the topic it covers
"""


class WebSearchSourceFinder(SourceFinder):
    name = "web search"

    def __init__(self, client: WebSearchClient, count: int = 8) -> None:
        self._client = client
        self._count = count

    def find(self, request: DiscoveryRequest) -> FinderResult:
        subtopics = ""
        if request.subtopics:
            subtopics = (
                "It involves these parts; try to cover each with at least one text:\n"
                + "\n".join(f"- {s}" for s in request.subtopics)
            )
        prompt = Prompt(
            SEARCH_TEMPLATE.format(count=self._count, topic=request.topic, subtopics=subtopics),
            system=SEARCH_SYSTEM,
        )
        try:
            response = self._client.search(prompt)
        except LLMError as exc:
            raise DiscoveryError(str(exc)) from exc
        sources = parse_found_sources(response.text, request.subtopics)[: self._count]
        return FinderResult(tuple(sources), response.total_tokens)


def parse_found_sources(text: str, subtopics: tuple[str, ...] = ()) -> list[FoundSource]:
    """The model's ``URL | title | author | year | part`` lines, each URL
    once. Missing fields are left empty; the part is matched to the
    closest of ``subtopics``, or left empty if it shares no word."""
    found: dict[str, FoundSource] = {}
    for line in text.splitlines():
        match = _SOURCE_LINE.search(line)
        if not match:
            continue
        url = match[1].rstrip(".,;)]")
        fields = [f.strip(" *\"'") for f in match[2].split("|")] + [""] * 4
        year = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", fields[2])
        subtopic = _closest(fields[3], subtopics)
        source = FoundSource(
            url=url,
            title=fields[0],
            author=fields[1],
            year=int(year[1]) if year else None,
            subtopic=subtopic,
        )
        found.setdefault(source.key, source)
    return list(found.values())


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) > 3}


def _closest(part: str, subtopics: tuple[str, ...]) -> str:
    """The subtopic sharing the most words with ``part``, the model's
    possibly reworded name for it."""
    words = _words(part)
    best, overlap = "", 0
    for subtopic in subtopics:
        if subtopic.lower() == part.lower():
            return subtopic
        shared = len(words & _words(subtopic))
        if shared > overlap:
            best, overlap = subtopic, shared
    return best
