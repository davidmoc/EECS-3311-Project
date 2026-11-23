"""Source discovery: finding texts beyond the library and adding them to it."""

from types import SimpleNamespace

import openai
import pytest

from praxis.discovery import (
    DiscoveryError,
    DiscoveryRequest,
    FinderResult,
    FoundSource,
    RawPage,
    SourceDiscoveryService,
    SourceFinder,
    WebPageReader,
    WebSearchSourceFinder,
    WikipediaSourceFinder,
    extract_page,
    parse_found_sources,
    wikipedia_text,
)
from praxis.discovery.service import document_id
from praxis.llm import LLMError, LLMResponse, OpenAIWebSearchAdapter, Prompt, WebSearchClient
from praxis.persistence import Database, SQLDocumentRepository

LIBYA_PARAGRAPHS = (
    "In March 2011 a NATO-led coalition began bombing Libya under the cover of "
    "Security Council resolution 1973, which had authorised only a no-fly zone.",
    "The destruction of the Libyan state left rival governments in Tripoli and "
    "Tobruk, each backed by foreign powers with interests in the country's oil.",
    "Libya holds the largest proven oil reserves in Africa, and control of the "
    "export terminals has been at stake in every round of fighting since.",
)


def article_html(paragraphs=LIBYA_PARAGRAPHS, title="Ten years after NATO destroyed Libya | Example Dispatch"):
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return f"""<html><head><title>{title}</title>
<meta property="og:site_name" content="Example Dispatch">
<meta name="author" content="A. Writer">
<meta property="article:published_time" content="2021-03-19T08:00:00Z">
<script>var tracking = "this is not prose and must never be kept at all";</script>
</head><body>
<nav><p>Home · World · Africa · Subscribe to our newsletter for weekly updates now</p></nav>
<article>{body}
<div class="share-buttons"><p>Share this article on every social network you can think of today</p></div>
</article>
<footer><p>Copyright Example Dispatch, all rights reserved, every year since its founding</p></footer>
</body></html>"""


def long_article_html():
    """Enough distinct prose to pass the reader's minimum length."""
    more = tuple(f"{p} (Part {n}.)" for n in range(2, 7) for p in LIBYA_PARAGRAPHS)
    return article_html(LIBYA_PARAGRAPHS + more)


# --- reading pages -------------------------------------------------------------

def test_a_page_keeps_the_article_prose_and_drops_the_furniture():
    page = extract_page(long_article_html(), "https://example.org/libya")

    assert page.title == "Ten years after NATO destroyed Libya"
    assert page.author == "A. Writer"
    assert page.site == "Example Dispatch"
    assert page.published.startswith("2021-03-19")
    assert page.text.split("\n\n")[0] == LIBYA_PARAGRAPHS[0]
    for junk in ("tracking", "Subscribe", "Share this", "Copyright"):
        assert junk not in page.text

    # Repeated paragraphs are kept once.
    twice = extract_page(article_html(LIBYA_PARAGRAPHS * 2), "https://example.org/libya")
    assert twice.text.count(LIBYA_PARAGRAPHS[0]) == 1


def test_a_page_without_an_article_element_uses_all_its_paragraphs():
    markup = "<html><body>" + "".join(f"<p>{p}</p>" for p in LIBYA_PARAGRAPHS) + "</body></html>"
    assert extract_page(markup, "https://example.org/x").text.count("\n\n") == 2


def test_reader_refuses_pages_with_too_little_text_and_non_html():
    short = WebPageReader(lambda url: RawPage(article_html().encode(), "text/html", url))
    with pytest.raises(DiscoveryError, match="too little readable text"):
        short.read("https://example.org/paywalled")

    pdf = WebPageReader(lambda url: RawPage(b"%PDF-1.7", "application/pdf", url))
    with pytest.raises(DiscoveryError, match="not a web page"):
        pdf.read("https://example.org/report.pdf")


def test_reader_decodes_the_declared_charset():
    markup = long_article_html().replace("Libya holds", "Libya – holds")
    reader = WebPageReader(lambda url: RawPage(markup.encode("cp1252"), "text/html; charset=windows-1252", url))
    assert "Libya – holds" in reader.read("https://example.org/x").text


# --- finders ---------------------------------------------------------------------

def test_web_search_lines_are_parsed_and_matched_to_subtopics():
    reply = """Here are some texts:
https://example.org/a | Libya and the Left | Peter Frase / Jacobin | 2011 | the 2011 NATO intervention
- https://example.org/b/ | Oil and the state | MERIP | 2019 | oil rent
https://example.org/a#comments | duplicate | x | 2011 | x
no link on this line | at all
https://example.org/c | Untitled
"""
    found = parse_found_sources(reply, ("The 2011 NATO intervention", "Oil-rent state"))

    assert [s.url for s in found] == ["https://example.org/a", "https://example.org/b/", "https://example.org/c"]
    assert found[0].title == "Libya and the Left"
    assert found[0].author == "Peter Frase / Jacobin"
    assert found[0].year == 2011
    assert found[0].subtopic == "The 2011 NATO intervention"
    assert found[1].subtopic == "Oil-rent state"
    assert found[2].subtopic == "" and found[2].year is None


class FakeWebSearch(WebSearchClient):
    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def search(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return LLMResponse(self.reply, "fake", 100, 20)


def test_web_search_finder_asks_for_the_topic_and_its_parts():
    client = FakeWebSearch("https://example.org/a | A | B | 2020 | oil")
    result = WebSearchSourceFinder(client, count=3).find(DiscoveryRequest("Libya", ("oil",)))

    assert result.tokens_used == 120
    assert [s.subtopic for s in result.sources] == ["oil"]
    assert "Libya" in client.prompts[0].user and "- oil" in client.prompts[0].user
    assert "Marxist" in client.prompts[0].user


def test_a_failed_web_search_is_a_discovery_error():
    finder = WebSearchSourceFinder(FakeWebSearch(LLMError("rate limited")))
    with pytest.raises(DiscoveryError, match="rate limited"):
        finder.find(DiscoveryRequest("Libya"))


WIKI_EXTRACT = (
    "Libya is a country in the Maghreb region of North Africa, bordered by the Mediterranean Sea.\n"
    "== History ==\n"
    + "Libya was an Italian colony from 1911 until 1943, when it came under Allied administration. " * 8
    + "\n\n== See also ==\nList of things\n== References ==\n1. A book"
)


def test_wikipedia_text_drops_headings_and_reference_sections():
    text = wikipedia_text(WIKI_EXTRACT)
    assert "==" not in text and "See also" not in text and "A book" not in text
    assert text.split("\n\n")[0].startswith("Libya is a country")


def test_wikipedia_finder_returns_articles_with_their_text():
    calls = []

    def fetch(url):
        calls.append(url)
        if "list=search" in url:
            return {"query": {"search": [{"title": "Libya"}]}}
        return {"query": {"pages": [{"title": "Libya", "extract": WIKI_EXTRACT,
                                     "fullurl": "https://en.wikipedia.org/wiki/Libya"}]}}

    result = WikipediaSourceFinder(fetch).find(DiscoveryRequest("Libya", ("Italian Libya",)))

    assert len(result.sources) == 1  # both searches found the same article
    source = result.sources[0]
    assert source.url == "https://en.wikipedia.org/wiki/Libya"
    assert source.license.startswith("CC BY-SA")
    assert source.subtopic == ""  # found first for the topic itself
    assert source.text.startswith("Libya is a country")


# --- the service -------------------------------------------------------------------

class FakeFinder(SourceFinder):
    def __init__(self, name, *sources, error=None, tokens=0):
        self.name = name
        self.sources = sources
        self.error = error
        self.tokens = tokens
        self.requests = []

    def find(self, request):
        self.requests.append(request)
        if self.error:
            raise DiscoveryError(self.error)
        return FinderResult(self.sources, self.tokens)


def page_reader(pages):
    """Serves ``pages`` (url -> html); any other url is a 404."""
    def fetch(url):
        if url not in pages:
            raise DiscoveryError("could not download it (HTTP Error 404)")
        return RawPage(pages[url].encode(), "text/html; charset=utf-8", url)

    return WebPageReader(fetch)


@pytest.fixture
def documents():
    database = Database()
    yield SQLDocumentRepository(database)
    database.close()


def test_discovered_pages_are_saved_as_articles_tagged_with_the_topic(documents):
    finder = FakeFinder("web", FoundSource("https://example.org/libya", subtopic="NATO war"), tokens=50)
    service = SourceDiscoveryService(documents, [finder], page_reader({"https://example.org/libya": long_article_html()}))

    report = service.discover("  Libya ", ["NATO war", "Libya", ""])

    assert finder.requests == [DiscoveryRequest("Libya", ("NATO war",))]
    assert [d.title for d in report.added] == ["Ten years after NATO destroyed Libya"]
    assert report.tokens_used == 50
    stored = documents.find_by_id(report.added[0].id)
    assert stored.kind == "article"
    assert stored.topics == ("Libya", "NATO war")
    assert stored.author == "A. Writer"
    assert stored.source_url == "https://example.org/libya"
    assert stored.publication_date.isoformat() == "2021-03-19"
    # Web pages are quoted only in excerpts and cannot be downloaded.
    assert not stored.can_reproduce() and not stored.downloadable
    assert "added them to your library" not in report.note() and "“Ten years after" in report.note()
    # The passages are now found by an ordinary library search.
    assert documents.search_passages("Tobruk oil")[0].document.id == stored.id


def test_texts_a_finder_supplies_are_reproducible_under_their_licence(documents):
    source = FoundSource("https://en.wikipedia.org/wiki/Libya", "Libya", "Wikipedia contributors",
                         text=wikipedia_text(WIKI_EXTRACT), license="CC BY-SA 4.0 (Wikipedia contributors)")
    report = SourceDiscoveryService(documents, [FakeFinder("wiki", source)], page_reader({})).discover("Libya")

    assert report.added[0].can_reproduce() and report.added[0].downloadable


def test_pages_already_in_the_library_are_not_fetched_again(documents):
    url = "https://example.org/libya"
    pages = {url: long_article_html()}
    service = SourceDiscoveryService(documents, [FakeFinder("web", FoundSource(url))], page_reader(pages))
    first = service.discover("Libya")
    pages.clear()  # a second download would now fail

    second = service.discover("Libya")

    assert second.added == () and [d.id for d in second.held] == [first.added[0].id]
    assert second.note() is None


def test_failures_are_reported_without_stopping_the_rest(documents):
    finders = [
        FakeFinder("broken", error="offline"),
        FakeFinder("web", FoundSource("https://example.org/gone"), FoundSource("https://example.org/libya")),
    ]
    service = SourceDiscoveryService(documents, finders, page_reader({"https://example.org/libya": long_article_html()}))

    report = service.discover("Libya")

    assert len(report.added) == 1
    assert ("broken", "offline") in report.failures
    assert any(url == "https://example.org/gone" for url, _ in report.failures)


def test_the_first_finders_copy_of_a_page_wins(documents):
    wiki = FoundSource("https://en.wikipedia.org/wiki/Libya", "Libya", text=wikipedia_text(WIKI_EXTRACT),
                       license="CC BY-SA 4.0")
    scraped = FoundSource("http://en.wikipedia.org/wiki/Libya/", "Libya - Wikipedia")
    service = SourceDiscoveryService(documents, [FakeFinder("wiki", wiki), FakeFinder("web", scraped)], page_reader({}))

    report = service.discover("Libya")

    assert [d.title for d in report.added] == ["Libya"]
    assert report.added[0].id == document_id(scraped.url)


def test_at_most_max_new_pages_are_read(documents):
    urls = [f"https://example.org/{n}" for n in range(5)]
    finder = FakeFinder("web", *(FoundSource(u) for u in urls))
    service = SourceDiscoveryService(documents, [finder], page_reader({u: long_article_html() for u in urls}), max_new=2)

    assert len(service.discover("Libya").added) == 2


def test_nothing_found_says_only_the_library_was_searched(documents):
    service = SourceDiscoveryService(documents, [FakeFinder("web", error="offline")], page_reader({}))
    assert "only the library was searched" in service.discover("Libya").note()


# --- the web search adapter ------------------------------------------------------------

class FakeResponses:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def response(text):
    return SimpleNamespace(output_text=text, model="m", usage=SimpleNamespace(input_tokens=7, output_tokens=3))


def test_web_search_adapter_uses_the_search_tool_at_low_effort():
    responses = FakeResponses(response("https://example.org | x"))
    adapter = OpenAIWebSearchAdapter("unused", "configured", client=SimpleNamespace(responses=responses))

    result = adapter.search(Prompt("find texts", system="be brief"))

    assert result.text == "https://example.org | x" and result.total_tokens == 10
    call = responses.calls[0]
    assert call["tools"] == [{"type": "web_search"}]
    assert call["reasoning"] == {"effort": "low"}
    assert call["instructions"] == "be brief" and call["input"] == "find texts"


def test_web_search_adapter_retries_without_reasoning_and_wraps_errors():
    bad = openai.BadRequestError("no reasoning", response=SimpleNamespace(status_code=400, headers={}, request=None), body=None)
    responses = FakeResponses(bad, response("ok"))
    adapter = OpenAIWebSearchAdapter("unused", "m", client=SimpleNamespace(responses=responses))
    assert adapter.search(Prompt("q")).text == "ok"
    assert "reasoning" not in responses.calls[1]

    failing = OpenAIWebSearchAdapter("unused", "m", client=SimpleNamespace(responses=FakeResponses(response(""))))
    with pytest.raises(LLMError, match="empty"):
        failing.search(Prompt("q"))
