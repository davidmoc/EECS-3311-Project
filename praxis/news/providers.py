"""Where current news comes from (F01, UC01, SD03's ``NewsProvider``).

``NewsProvider`` is the application's own interface for a news source.
``RSSNewsAdapter`` adapts one RSS or Atom feed to it, so the rest of the
system only ever sees ``NewsArticle`` documents.

Only what the feed publishes for syndication is kept: the headline, the
summary, the link, the date, the author and the categories. The article
itself stays on the outlet's site, so the licence marks the text as not
reproducible and quotations from it stay short.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ElementTree
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from praxis.documents import NewsArticle

DEFAULT_FEEDS = Path(__file__).resolve().parents[2] / "data" / "news" / "feeds.json"
# Longest summary kept from a feed; some feeds put the whole article there.
MAX_SUMMARY_CHARS = 1500
MAX_CATEGORIES = 8
USER_AGENT = "Praxis/0.1 (course project; RSS reader)"

_TAG = re.compile(r"<[^>]+>")
# Paragraph breaks in feed HTML, kept so the summary keeps its paragraphs.
_BREAK = re.compile(r"</p\s*>|<br\s*/?>", re.IGNORECASE)
# Links back to the full article that some feeds append ("Continue reading...").
_BOILERPLATE = re.compile(r"^(continue reading|read more)\W*$", re.IGNORECASE)


class NewsProviderError(Exception):
    """A news source could not supply its articles."""


@dataclass(frozen=True)
class FeedSource:
    id: str
    outlet: str
    url: str


class NewsProvider(ABC):
    name: str

    @abstractmethod
    def get_recent_news(self) -> list[NewsArticle]:
        """The source's current articles, or raise ``NewsProviderError``."""


Fetcher = Callable[[str], bytes]


def _http_get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise NewsProviderError(f"Could not download {url}: {exc}") from exc


class RSSNewsAdapter(NewsProvider):
    """Adapter for one RSS 2.0, RSS 1.0 (RDF) or Atom feed.

    ``fetcher`` turns a URL into bytes; tests pass a fake so they never
    touch the network.
    """

    def __init__(self, feed: FeedSource, fetcher: Fetcher = _http_get) -> None:
        self.feed = feed
        self.name = feed.outlet
        self._fetch = fetcher

    def get_recent_news(self) -> list[NewsArticle]:
        return parse_feed(self._fetch(self.feed.url), self.feed)


def parse_feed(data: bytes, feed: FeedSource) -> list[NewsArticle]:
    """The articles in a feed document. Items without a title or link are
    skipped; a document that is not a feed raises ``NewsProviderError``."""
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise NewsProviderError(f"{feed.outlet}: the feed could not be read ({exc}).") from exc
    if _local(root.tag) not in ("rss", "RDF", "feed"):
        raise NewsProviderError(f"{feed.outlet}: {feed.url} is not an RSS or Atom feed.")
    articles = []
    for element in root.iter():
        if _local(element.tag) in ("item", "entry"):
            article = _article(element, feed)
            if article is not None:
                articles.append(article)
    return articles


def _article(item: ElementTree.Element, feed: FeedSource) -> NewsArticle | None:
    title = _plain(_text(item, "title"))
    link = _link(item)
    if not title or not link:
        return None
    summary = _summary(_text(item, "description", "summary", "content", "encoded"))
    published = _published(_text(item, "pubDate", "date", "published", "updated"))
    categories = [_plain(c.text or c.get("term", "")) for c in item if _local(c.tag) == "category"]
    author = _plain(_text(item, "creator", "author")) or feed.outlet
    return NewsArticle(
        # Same link, same id: fetching the feed again updates the article.
        id=uuid5(NAMESPACE_URL, link),
        title=title,
        author=author,
        outlet=feed.outlet,
        text=summary,
        publication_date=published,
        source_url=link,
        license=f"© {feed.outlet}; feed summary only",
        downloadable=False,
        topics=tuple(dict.fromkeys(c for c in categories if c))[:MAX_CATEGORIES],
    )


def _local(tag: str) -> str:
    """``{http://www.w3.org/2005/Atom}entry`` → ``entry``."""
    return tag.rsplit("}", 1)[-1]


def _text(item: ElementTree.Element, *names: str) -> str:
    """The text of the first child named any of ``names``, in that order."""
    children = {}
    for child in item:
        children.setdefault(_local(child.tag), child)
    for name in names:
        child = children.get(name)
        if child is not None:
            # Atom <author><name>…</name></author>
            if name == "author" and len(child):
                return "".join(child.itertext())
            if child.text and child.text.strip():
                return child.text
    return ""


def _link(item: ElementTree.Element) -> str:
    for child in item:
        if _local(child.tag) == "link":
            href = child.get("href") or (child.text or "")
            if href.strip() and child.get("rel", "alternate") == "alternate":
                return href.strip()
    return _text(item, "guid").strip() if _text(item, "guid").startswith("http") else ""


def _plain(text: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", text)).split())


def _summary(markup: str) -> str:
    """Feed HTML as plain paragraphs separated by blank lines."""
    paragraphs = [_plain(part) for part in _BREAK.split(markup)]
    text = "\n\n".join(p for p in paragraphs if p and not _BOILERPLATE.match(p))
    if len(text) > MAX_SUMMARY_CHARS:
        text = text[:MAX_SUMMARY_CHARS].rsplit(" ", 1)[0] + " …"
    return text


def _published(value: str) -> date | None:
    """RFC 822 (``Sun, 22 Nov 2026 18:50:56 GMT``) or ISO 8601 dates, as
    the UTC calendar date."""
    value = value.strip()
    if not value:
        return None
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    return moment.date()


def read_feeds(path: Path | str = DEFAULT_FEEDS) -> list[FeedSource]:
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))
        return [FeedSource(e["id"], e["outlet"], e["url"]) for e in entries]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise NewsProviderError(f"Cannot read the feed list {path}: {exc}") from exc
