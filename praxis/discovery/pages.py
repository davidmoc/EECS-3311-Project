"""Reading a found web page as a library text.

``WebPageReader`` downloads a page and keeps its main prose: the
paragraphs inside ``<article>`` or ``<main>`` when the page has them,
without navigation, scripts, footers, sidebars or share buttons. Pages
with too little prose (paywalls, pages built by scripts, PDFs) are
refused rather than stored half-empty.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

from praxis.discovery.finders import DiscoveryError

USER_AGENT = "Mozilla/5.0 (compatible; Praxis/0.1; course project research reader)"
MAX_PAGE_BYTES = 3_000_000
MAX_TEXT_CHARS = 250_000
MIN_TEXT_CHARS = 1500
MIN_PARAGRAPH_CHARS = 60

_SKIPPED = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form",
            "svg", "button", "figure", "template", "iframe", "select"}
_BLOCKS = {"p", "blockquote", "li", "pre", "h1", "h2", "h3", "h4", "dd"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
         "source", "track", "wbr"}
# Class or id names of page furniture inside the article ("share-bar",
# "related-posts"). Only names that start with one count, so a wrapper
# such as "has-sidebar" is not mistaken for a sidebar.
_FURNITURE = re.compile(
    r"^(share|sharing|social|related|newsletter|subscribe|comment|advert|promo|"
    r"cookie|sidebar|breadcrumb|signup|paywall)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WebPage:
    url: str
    title: str
    text: str
    author: str = ""
    site: str = ""
    published: str = ""  # as the page gives it, e.g. "2024-03-01T10:00:00Z"


@dataclass(frozen=True)
class RawPage:
    body: bytes
    content_type: str
    url: str  # after redirects


PageFetcher = Callable[[str], RawPage]


def _http_get(url: str) -> RawPage:
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return RawPage(
                response.read(MAX_PAGE_BYTES),
                response.headers.get("Content-Type", ""),
                response.geturl(),
            )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise DiscoveryError(f"could not download it ({exc})") from exc


class WebPageReader:
    """``fetcher`` turns a URL into a ``RawPage``; tests pass a fake."""

    def __init__(self, fetcher: PageFetcher = _http_get) -> None:
        self._fetch = fetcher

    def read(self, url: str) -> WebPage:
        raw = self._fetch(url)
        content_type = raw.content_type.lower()
        if content_type and "html" not in content_type:
            kind = content_type.split(";")[0].strip()
            raise DiscoveryError(f"it is not a web page ({kind})")
        page = extract_page(_decode(raw.body, content_type), raw.url or url)
        if len(page.text) < MIN_TEXT_CHARS:
            raise DiscoveryError(
                "too little readable text (behind a paywall, or built by scripts)"
            )
        return page


def _decode(body: bytes, content_type: str) -> str:
    charset = re.search(r"charset=([\w-]+)", content_type)
    if charset is None:
        charset = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', body[:4096], re.IGNORECASE)
        name = charset[1].decode("ascii") if charset else "utf-8"
    else:
        name = charset[1]
    try:
        return body.decode(name, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


class _ProseParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []  # (tag, skipped here)
        self.skip_depth = 0
        self.main_depth = 0
        self.block: list[str] | None = None
        self.block_in_main = False
        self.paragraphs: list[tuple[str, bool]] = []  # (text, inside article/main)
        self.title = ""
        self.in_title = False
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (values.get("property") or values.get("name") or values.get("itemprop") or "").lower()
            if key and values.get("content"):
                self.meta.setdefault(key, values["content"].strip())
            return
        if tag in _VOID:
            return
        if tag == "title" and not self.title:
            self.in_title = True
        names = (values.get("class", "") + " " + values.get("id", "")).split()
        furniture = tag not in ("html", "body", "article", "main") and any(
            _FURNITURE.match(name) for name in names
        )
        skipped = tag in _SKIPPED or furniture
        if skipped:
            self.skip_depth += 1
        if tag in ("article", "main") or values.get("role") == "main":
            self.main_depth += 1
            tag = tag if tag in ("article", "main") else f"{tag}#main"
        self.stack.append((tag, skipped))
        if tag in _BLOCKS and self.skip_depth == 0:
            self._close_block()
            self.block = []
            self.block_in_main = self.main_depth > 0

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag in _VOID or not any(t.split("#")[0] == tag for t, _ in self.stack):
            return
        # Close everything opened since the matching start tag (HTML often
        # leaves <li> and <p> unclosed).
        while self.stack:
            open_tag, skipped = self.stack.pop()
            if skipped:
                self.skip_depth -= 1
            if open_tag in ("article", "main") or open_tag.endswith("#main"):
                self.main_depth -= 1
            if open_tag in _BLOCKS:
                self._close_block()
            if open_tag.split("#")[0] == tag:
                break

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        if self.block is not None and self.skip_depth == 0:
            self.block.append(data)

    def _close_block(self) -> None:
        if self.block is not None:
            text = " ".join("".join(self.block).split())
            if text:
                self.paragraphs.append((text, self.block_in_main))
        self.block = None

    def close(self) -> None:
        super().close()
        self._close_block()


def extract_page(markup: str, url: str) -> WebPage:
    parser = _ProseParser()
    parser.feed(markup)
    parser.close()
    meta = parser.meta

    in_main = [text for text, inside in parser.paragraphs if inside]
    chosen = in_main if sum(map(len, in_main)) >= MIN_TEXT_CHARS else [t for t, _ in parser.paragraphs]
    paragraphs = list(dict.fromkeys(p for p in chosen if len(p) >= MIN_PARAGRAPH_CHARS))
    text = "\n\n".join(paragraphs)
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS].rsplit("\n\n", 1)[0]

    site = meta.get("og:site_name", "") or urlsplit(url).netloc.removeprefix("www.")
    title = meta.get("og:title") or meta.get("twitter:title") or " ".join(parser.title.split())
    # "Headline | Outlet" titles: keep the headline.
    owner = _squash(site + " " + urlsplit(url).netloc)
    for separator in (" | ", " – ", " — ", " - ", " : "):
        head, _, tail = title.rpartition(separator)
        if head and len(_squash(tail)) >= 3 and _squash(tail) in owner:
            title = head
            break
    author = meta.get("author") or meta.get("article:author") or meta.get("parsely-author") or ""
    if author.startswith("http"):
        author = ""
    published = (meta.get("article:published_time") or meta.get("datepublished")
                 or meta.get("date") or meta.get("dc.date") or "")
    return WebPage(url, title.strip(), text, author.strip(), site.strip(), published.strip())


def _squash(text: str) -> str:
    """Letters and digits only, lower case: "Peoples Dispatch" and
    "peoplesdispatch.org" then share "peoplesdispatch"."""
    return re.sub(r"[^a-z0-9]", "", text.lower())
